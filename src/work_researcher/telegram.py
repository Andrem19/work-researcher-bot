"""Telegram Bot API delivery and HTML report rendering."""

from __future__ import annotations

import html
from collections.abc import Iterable
from datetime import datetime

import httpx

from .config import Settings


def _value(value) -> str:
    if value in (None, "", []):
        return "не указано"
    if isinstance(value, list):
        return "; ".join(html.escape(str(x)) for x in value) or "не указано"
    return html.escape(str(value))


def render_report(jobs: list[dict], provider_health: list[dict], cv_sync: dict, run_time: datetime) -> list[str]:
    ok_sources = [x["provider"] for x in provider_health if x.get("ok")]
    warnings = [
        f"{x['provider']}: {x.get('error', 'error')}"
        for x in provider_health if x.get("error")
    ]
    header = (
        f"<b>Вечерний поиск вакансий — {run_time:%d.%m.%Y}</b>\n"
        f"Новых вакансий после жёстких фильтров: <b>{len(jobs)}</b>\n"
        f"CV обновлены из Drive: <b>{len(cv_sync.get('files', []))}</b>\n"
        f"Источники: {_value(ok_sources)}"
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
        block = (
            f"<b>{index}. {title_line}</b>\n"
            f"<b>{tier}</b>\n"
            f"🏢 <b>Работодатель:</b> {_value(job.get('company'))} — прямой ({_value(job.get('direct_employer_reason'))})\n"
            f"🧭 <b>Линия:</b> {_value(job.get('path_label'))} | <b>Score:</b> {_value(job.get('overall_score'))}/100\n"
            f"📍 <b>Место:</b> {_value(job.get('location_text'))} | <b>Формат:</b> {_value(job.get('work_mode'))}\n"
            f"💷 <b>Зарплата:</b> {_value(salary)}\n"
            f"📝 <b>Суть:</b> {_value(job.get('summary_ru'))}\n"
            f"❗ <b>Обязательные требования:</b> {_value(job.get('mandatory_requirements'))}\n"
            f"<b>Desirable:</b> {_value(job.get('desirable_requirements'))}\n"
            f"⚙️ <b>Особые условия:</b> {_value(job.get('special_conditions'))}\n"
            f"✅ <b>Что подходит в CV:</b> {_value(job.get('cv_strengths'))}\n"
            f"⚠️ <b>Пробелы/риски:</b> {_value(job.get('cv_gaps'))}\n"
            f"🚩 <b>Замечания модели:</b> {_value(job.get('rejection_reasons'))}\n"
            f"📄 <b>CV:</b> {_value(job.get('cv_filename'))}\n"
            f"🔎 <b>Источник:</b> {_value(job.get('source'))}"
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
