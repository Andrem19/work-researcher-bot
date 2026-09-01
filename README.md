# Work Researcher Bot

Серверный агент поиска работы для одного кандидата — Andrey Remnev. Каждый
вечер в 22:00 по времени United Kingdom он обновляет четыре профильных CV из
публичной папки Google Drive, ищет entry-level вакансии, фильтрует агентства и
неподходящую географию, оценивает вакансии через `glm-5.3-flash` и отправляет
ранжированный HTML-отчёт в Telegram.

## Четыре карьерные линии

1. Data Engineering
2. Geospatial Data Engineering
3. Analytics → Data Engineering
4. Software Engineering → Data Platform

Ищутся junior, trainee, graduate, associate и Level 1 роли без требования
значительного подтверждённого опыта. AI/MLOps остаётся последующей надстройкой,
а не отдельной пятой линией.

## Политика отбора

- только прямые работодатели; агентства и recruitment consultancies исключаются;
- remote — вся Великобритания;
- on-site — Blackpool, Preston и ближайшие населённые пункты;
- hybrid — расширенная зона до Manchester и сопоставимых городов;
- senior/lead/manager роли, требования 3+ лет и платные training/course ads
  исключаются;
- GLM ранжирует, проверяет обязательные и желательные требования, специальные
  условия, соответствие выбранному CV и формирует русское резюме; он не может
  исключить vacancy, уже прошедшую жёсткие фильтры;
- уже доставленные вакансии хранятся в SQLite и повторно не отправляются.

## Runtime

```text
22:00 Europe/London
  -> public Google Drive: download + validate exactly four non-geology CVs
  -> configured job providers, включая GOV.UK Find a job и Civil Service Careers
  -> deterministic entry/location/agency filters
  -> GLM-5.3-Flash structured assessment and ranking
  -> Telegram HTML header + one detailed vacancy card per message
  -> delivery state saved only after Telegram succeeds
```

Telegram-отчёт содержит максимум 10 вакансий: первые 5 приходят полными
карточками с требованиями и анализом CV, позиции 6–10 — сокращёнными карточками
с ключевыми данными и ссылкой.

## Локальные команды

```bash
uv sync --extra dev
uv run work-researcher doctor
uv run work-researcher sync-drive
uv run work-researcher run-once --dry-run
uv run pytest -q
```

Скопируйте `config.example.toml` в `config.toml`. Секреты задаются только через
переменные окружения: `ZAI_API_KEY`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID` и необязательные API-ключи job boards.

## Доставка

Push в `main` запускает `.github/workflows/deploy.yml`: тесты, сборку release,
SSH-загрузку на сервер и атомарное переключение `/opt/work-researcher-bot/current`.
Systemd timer использует `Europe/London`, поэтому BST/GMT учитываются
автоматически. Подробности — в `SETUP.md`.

## Отделённый application-контур

Унаследованные MCP-инструменты для браузера и подачи заявок сохранены в
`server.py`, но nightly-сервис их не импортирует и не запускает. Их можно
использовать вручную/локально через `work-researcher serve`; автоматическая
подача заявок на сервере не входит в этот runtime.

## Основные компоненты

```text
src/work_researcher/bot.py       nightly orchestration
src/work_researcher/drive.py     public Drive CV snapshot
src/work_researcher/career.py    hard eligibility filters
src/work_researcher/llm.py       GLM structured assessment
src/work_researcher/telegram.py  Telegram HTML reports
src/work_researcher/providers/   vacancy sources
src/work_researcher/server.py    separate local MCP/application surface
deploy/                          systemd configuration and activation
```

License: MIT.
