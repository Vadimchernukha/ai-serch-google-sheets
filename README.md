# Top Scraper

CLI для массового обогащения данных о компаниях из Google Sheets.

## Быстрый старт

1. `python3 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Скопируй `config/env.example` в `.env` и заполни ключи.
4. `playwright install chromium`
5. `python -m src.main --limit 10` (для теста на первых строках)

Файл `commands.md` содержит эти и дополнительные команды в одном месте.

## Архитектура

- `src/config.py` — загрузка настроек из .env (pydantic).
- `src/google_sheet.py` — чтение/запись Google Sheets, бэкапы.
- `src/pipeline/enricher.py` — основной пайплайн обогащения.
- `src/sources/` — HTTP-скрапинг и внешние API (SerpAPI, NewsAPI).
- `src/nlp/llm.py` — обёртка вокруг OpenAI/Perplexity для саммари.
- `src/utils/` — нормализация данных, эвристики.
- `reports/` — локальные бэкапы JSON/CSV после запуска.
- `commands.md` — шпаргалка с командами запуска.

## Запуск

```bash
python -m src.main --limit 50 --resume
```

Флаги `--limit` и `--resume` опциональны. Логирование идёт в консоль, ошибки пишутся вместе с трейсами.

## Переменные окружения

Смотри `config/env.example`. Ключи Google берутся из JSON сервисного аккаунта в виде строки целиком.

## Использование Perplexity

Укажи `PERPLEXITY_API_KEY`, если нужно fallback на Perplexity для саммари или поиска новостей, когда сайт не даёт данных.
# Top Scraper

Консольный инструмент для обогащения списка компаний из Google Sheets свежими сводками, инсайтами, новостями и продуктовой информацией.

## Быстрый старт

1. Создай виртуальное окружение и установи зависимости:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   ```

2. Скопируй `env.template` в `.env` и заполни переменные (JSON сервисного аккаунта, ID таблицы и т.д.).

3. Запусти CLI (при старте спросит профиль `software` или `iso_msp`, затем режим basic/extended):

   ```bash
   python -m src.main --profile software --limit 20
   ```

   Дополнительные флаги смотри в `python -m src.main --help`.

## Архитектура

- `src/main.py` — точка входа, аргументы, прогресс, файлы отчётов
- `src/config.py` — загрузка .env, валидация настроек
- `src/google_sheet.py` — работа с Google Sheets API
- `src/pipeline/enricher.py` — основной конвейер обогащения
- `src/sources/*` — клиенты для сайтов и внешних API (SerpAPI, NewsAPI, Apify LinkedIn)
- `src/nlp/llm.py` — генерация саммари и инсайтов
- `src/utils/text.py` — утилиты обработки текста

## TODO

- добавить кэширование результатов API (sqlite/redis)
- прикрутить юнит-тесты для парсеров
- расширить детект продуктов

## Колонки результата

- `summary`, `insights` — LLM-конспекты.
- `has_software`, `software_products` — индикатор и список исключительно софтверных продуктов.
- `business_model`, `market_focus` — классификация модели и сегмента (B2B/B2C/...).
- `latest_news`, `articles`, `linkedin_posts` — появляются в extended-режиме.
- `iso_category`, `services`, `merchant_segments`, `geography`, `partnerships` — появляются при профиле `iso_msp`.

