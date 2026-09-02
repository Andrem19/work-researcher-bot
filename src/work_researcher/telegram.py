"""Telegram Bot API delivery and HTML report rendering."""

from __future__ import annotations

import html
from collections import Counter
from collections.abc import Iterable
from datetime import datetime

import httpx

from .config import Settings


def _value(value, *, max_items: int | None = None, max_chars: int | None = None) -> str:
    if value in (None, "", []):
        return "не указано"
    if isinstance(value, list):
        values = value[:max_items] if max_items is not None else value
        text = "; ".join(str(x) for x in values) or "не указано"
    else:
        text = str(value)
    if max_chars is not None and len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return html.escape(text)


def _work_mode(value: str | None) -> str:
    return {
        "remote": "remote",
        "hybrid": "гибрид",
        "on_site": "офис",
    }.get(value or "", value or "не указано")


def _source_name(value: str | None) -> str:
    return {
        "findajob": "Find a Job (GOV.UK)",
        "civil_service": "Civil Service Careers",
        "reed": "Reed",
        "totaljobs": "Totaljobs",
        "earthworks": "Earthworks",
        "adzuna": "Adzuna",
        "jooble": "Jooble",
    }.get(value or "", value or "не указано")


def render_report(
    jobs: list[dict],
    provider_health: list[dict],
    cv_sync: dict,
    run_time: datetime,
    *,
    detailed_jobs: int = 5,
) -> list[str]:
    ok_sources = [_source_name(x["provider"]) for x in provider_health if x.get("ok")]
    result_sources = Counter(_source_name(job.get("source")) for job in jobs)
    result_source_text = ", ".join(
        f"{source}: {count}" for source, count in result_sources.items()
    ) or "нет"
    warnings = [
        f"{x['provider']}: {x.get('error', 'error')}"
        for x in provider_health if x.get("error")
    ]
    header = (
        f"<b>Вечерний поиск вакансий — {run_time:%d.%m.%Y}</b>\n"
        f"Показано лучших вакансий после жёстких фильтров: <b>{len(jobs)}</b>\n"
        f"CV обновлены из Drive: <b>{len(cv_sync.get('files', []))}</b>\n"
        f"Источники поиска: {_value(ok_sources)}\n"
        f"Источники в топе: {_value(result_source_text)}"
    )
    if len(jobs) > detailed_jobs:
        header += (
            f"\nФормат: первые <b>{detailed_jobs}</b> подробно, "  # noqa: RUF001
            f"следующие <b>{len(jobs) - detailed_jobs}</b> кратко"
        )
    if warnings:
        header += f"\n⚠️ Ограничения источников: {_value(warnings)}"
    messages = [header]
    for index, job in enumerate(jobs, 1):
        url = html.escape(job.get("url") or "", quote=True)
        title = html.escape(job.get("title") or "Без названия")
        title_line = f'<a href="{url}">{title}</a>' if url else title
        salary = job.get("salary_raw") or "не указана"
        tier = {
            "strong": "✅ Сильная рекомендация модели",
            "review": "🟡 Прошла фильтры — стоит рассмотреть",
            "fallback": "🟠 Прошла фильтры — решение оставлено вам",
        }.get(job.get("review_tier"), "🟡 Прошла фильтры — стоит рассмотреть")
        common = (
            f"<b>{index}. {title_line}</b>\n"
            f"<b>{tier}</b>\n"
            f"🏢 <b>Работодатель:</b> {_value(job.get('company'))}\n"
            f"🧭 <b>Линия:</b> {_value(job.get('path_label'))} | <b>Score:</b> {_value(job.get('overall_score'))}/100\n"
            f"📍 <b>Место:</b> {_value(job.get('location_text'))} | <b>Формат:</b> {_value(_work_mode(job.get('work_mode')))}\n"
            f"💷 <b>Зарплата:</b> {_value(salary, max_chars=100)}\n"
            + f"⏳ <b>Срок {'работодателя' if job.get('deadline_kind') == 'employer' else 'по объявлению'}:</b> {_value(job.get('deadline_at') or job.get('deadline'))}"
            + (" (год выведен из текущей даты)" if job.get("deadline_year_inferred") else "")
            + "\n"
        )
        check = job.get("application_check")
        if check == "unverified":
            common += "⚠️ Приём заявок не подтверждён; страницу подачи проверить вручную.\n"
        elif check == "listing_checked":
            common += "🔎 Карточка площадки проверена; срок работодателя может отличаться.\n"
        elif check == "employer_listing":
            common += "🔎 Срок подтверждён в каталоге работодателя.\n"
        elif check == "application_page_checked":
            common += "🔎 Страница подачи проверена.\n"
        if job.get("deadline_conflict"):
            common += "⚠️ Сроки в источниках расходятся; использован срок работодателя или более ранний.\n"
        deadline_source = job.get("deadline_source_url")
        if deadline_source:
            common += f'<a href="{html.escape(deadline_source, quote=True)}">Источник срока</a>\n'
        if index <= detailed_jobs:
            block = (
                common
                + f"🎯 <b>Почему в топе:</b> {_value(job.get('rank_reason_ru'), max_chars=220)}\n"
                + f"📝 <b>Суть:</b> {_value(job.get('summary_ru'), max_chars=300)}\n"
                + f"🌱 <b>Entry-сигналы:</b> {_value(job.get('entry_evidence'), max_items=3, max_chars=180)}\n"
                + f"❗ <b>Обязательно:</b> {_value(job.get('mandatory_requirements'), max_items=4, max_chars=260)}\n"
                + f"+ <b>Желательно:</b> {_value(job.get('desirable_requirements'), max_items=3, max_chars=180)}\n"
                + f"✅ <b>CV-fit:</b> {_value(job.get('cv_strengths'), max_items=3, max_chars=180)}\n"
                + f"⚠️ <b>Пробелы:</b> {_value(job.get('cv_gaps'), max_items=3, max_chars=180)}\n"
                + f"⚙️ <b>Особые условия:</b> {_value(job.get('special_conditions'), max_items=2, max_chars=160)}\n"
                + f"🔐 <b>Работодатель:</b> {_value(job.get('direct_employer_reason'), max_chars=100)}\n"
                + f"🚩 <b>Замечания:</b> {_value(job.get('rejection_reasons'), max_items=2, max_chars=160)}\n"
                + f"📄 <b>CV:</b> {_value(job.get('cv_filename'))}\n"
                + f"🔎 <b>Источник:</b> {_value(_source_name(job.get('source')))}"
            )
        else:
            block = (
                common
                + f"🎯 <b>Почему:</b> {_value(job.get('rank_reason_ru'), max_chars=180)}\n"
                + f"⚠️ <b>Нюанс:</b> {_value(job.get('main_tradeoff_ru'), max_chars=140)}\n"
                + f"📄 <b>CV:</b> {_value(job.get('cv_filename'))} | "
                + f"🔎 <b>Источник:</b> {_value(_source_name(job.get('source')))}"
            )
        if len(block) > 3900:
            block = block[:3850] + "…"
        messages.append(block)
    if not jobs:
        messages.append("Сегодня новых вакансий, прошедших все жёсткие фильтры, нет.")
    return messages


def render_failure(exc: BaseException) -> str:
    """Render a bounded operational alert without credentials or tracebacks."""
    detail = str(exc).replace("<", "[").replace(">", "]")[:1000]
    return (
        "<b>⚠️ Вечерний поиск вакансий завершился с ошибкой</b>\n"  # noqa: RUF001
        f"<b>Тип:</b> {_value(type(exc).__name__)}\n"
        f"<b>Детали:</b> {_value(detail)}\n"
        "Сервис повторит работу при следующем запуске; ошибка сохранена в журнале сервера."
    )


async def send_messages(settings: Settings, messages: Iterable[str]) -> list[int]:
    if not settings.telegram_token or not settings.telegram_chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured")
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    ids = []
    async with httpx.AsyncClient(timeout=30) as client:
        for message in messages:
            response = await client.post(url, json={
                "chat_id": settings.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": bool(settings.telegram.get("disable_web_page_preview", True)),
            })
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                raise RuntimeError(f"Telegram rejected message: {payload.get('description')}")
            ids.append(int(payload["result"]["message_id"]))
    return ids
