# Work Researcher Bot

Серверный агент поиска работы для одного кандидата — Andrey Remnev. Каждый
вечер в 20:00 по времени United Kingdom он обновляет четыре профильных CV из
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
  условия, соответствие выбранному CV и формирует русское резюме; после
  пакетной проверки отдельный проход сравнивает весь shortlist на единой шкале;
  модель ищет явные entry-сигналы (обучение, mentoring, приглашение кандидатов,
  которые соответствуют не всем критериям) и не может исключить vacancy, уже
  прошедшую жёсткие фильтры;
- вакансии с явной пометкой closed/expired или истёкшим указанным closing date
  исключаются до отчёта, а близкий deadline повышает срочность рассмотрения;
- уже доставленные вакансии хранятся в SQLite и повторно не отправляются.
- линия определяется по названию и содержанию вакансии, независимо от поискового
  запроса; только после этого выбирается соответствующий CV;
- Reed учитывает локальную географию, фильтр direct employers и пагинацию.
  Мягкие квоты в shortlist и топе сохраняют разнообразие источников/линий,
  но не оставляют пустые места, если других подходящих вариантов нет.

## Runtime

Перед GLM бот заново открывает все прошедшие фильтры объявления и цепочки
ссылок подачи (только GET; без отправки заявок). Срок работодателя приоритетнее
срока размещения на площадке; сохраняются источник, время проверки и расхождения.
Проверяются `validThrough`, даты/время по Europe/London, 404/410 и closed/expired.
Год, отсутствующий в объявлении, принимается текущим и явно помечается в отчёте.
CAPTCHA, недоступная или JS-only страница не считаются подтверждением приёма:
такие варианты помечаются предупреждением, а при сроке закрытия сегодня
удерживаются из отчёта до подтверждения. GLM не может переписать эти факты.
Перед отправкой срок повторно сравнивается с текущим временем.

В каждой Telegram-карточке (включая краткие 6–10) есть строки «Опубликовано» и
«Дедлайн». Для дублей сравниваются даты на найденных площадках и связанных
страницах работодателя: основной становится самая ранняя известная публикация.
Отдельная таблица `vacancy_publications` хранит доказательства по каждому URL,
поэтому перепубликация и более длинное описание не затирают раннюю дату.
`first_seen`, дата скачивания и `dateModified`/Jooble `updated` публикацией не
считаются. Приблизительные даты и отсутствующий год помечаются; при равенстве
дат без времени не заявляется, какая площадка была первой в течение дня.
Это самая ранняя дата **среди найденных источников**, а не доказательство
первой публикации во всём интернете. Если старая копия закрыта, она остаётся
ссылкой-источником даты, а основная ссылка ведёт на актуальную копию.

Повторная проверка сохранённого отчёта без GLM и Telegram:

```bash
uv run python scripts/verify_report_freshness.py /path/to/nightly-runs/report.json
```

```text
20:00 Europe/London
  -> public Google Drive: download + validate exactly four non-geology CVs
  -> national queries + отдельные Blackpool/Preston/Lancashire/Manchester queries
     across configured providers, включая GOV.UK Find a job и Civil Service Careers
  -> deterministic entry/location/agency filters
  -> advert + application-link freshness verification
  -> GLM-5.3-Flash full-description assessment
  -> one global comparative rerank of every hard-filtered candidate
  -> Telegram HTML header + one detailed vacancy card per message
  -> delivery state saved only after Telegram succeeds
```

Telegram-отчёт содержит максимум 10 вакансий: первые 5 приходят полными
карточками с требованиями и анализом CV, позиции 6–10 — сокращёнными карточками
с ключевыми данными и ссылкой.
Точная копия сформированного отчёта, распределение источников и Telegram message IDs
сохраняются в `data/nightly-runs/` для последующего аудита качества.

## Еженедельное исследование рынка

Каждую пятницу в 20:00 UK time отдельный `work-researcher-market.timer`
исследует рынок по матрице 4 карьерных направления × 3 уровня: Entry, Middle и
High-paying (£80k+). GLM-5.3-Flash подтверждает релевантность и уровень роли,
а воспроизводимый Python-анализ рассчитывает спрос на технологии, salary
coverage, P25/P50/P75, распределение по квартилям и наиболее частые/дорогие
пары и тройки технологий. Поиск использует 90-дневное rolling window и
расширенную сетку из 90 role-запросов. История сохраняет до 104 недель спроса
и медианной зарплаты для каждой технологии и комбинации.

Последний snapshot и история хранятся вне release в
`/var/lib/work-researcher-bot/market`. Dashboard публикуется существующим Nginx:
<https://devbot.remart.ovh/jobs/>.

## Локальные команды

```bash
uv sync --extra dev
uv run work-researcher doctor
uv run work-researcher sync-drive
uv run work-researcher run-once --dry-run
uv run work-researcher weekly-market
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
src/work_researcher/market.py    weekly market statistics and publication
src/work_researcher/telegram.py  Telegram HTML reports
dashboard/index.html             static interactive market dashboard
src/work_researcher/providers/   vacancy sources
src/work_researcher/server.py    separate local MCP/application surface
deploy/                          systemd configuration and activation
```

License: MIT.
