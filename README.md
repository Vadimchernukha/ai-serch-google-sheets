# Top Scraper

CLI для массового обогащения данных о компаниях из Google Sheets.

## Быстрый старт

1. `python3 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Скопируй `config/env.example` в `.env` и заполни ключи.
4. `playwright install chromium`
5. `python -m src.cli scrape --limit 10` (для теста на первых строках)

Файл `commands.md` содержит эти и дополнительные команды в одном месте.

## Архитектура

- `src/cli.py` — Typer-CLI с тремя этапами
- `src/config.py` — загрузка настроек из .env (pydantic).
- `src/google_sheet.py` — чтение/запись Google Sheets, бэкапы.
- `src/pipeline/enricher.py` — основной пайплайн обогащения.
- `src/sources/` — HTTP-скрапинг и внешние API (SerpAPI, NewsAPI).
- `src/nlp/llm.py` — обёртка вокруг OpenAI/Perplexity для саммари.
- `src/utils/` — нормализация данных, эвристики.
- `reports/` — локальные бэкапы JSON/CSV после запуска.
- `commands.md` — шпаргалка с командами запуска.

## Этапы запуска

```bash
# Stage 1: базовый сбор (baseline_summary, фильтры, is_relevant)
python -m src.cli scrape --profile software --resume

# Stage 2: новости/статьи/LinkedIn (хайлайты, сигнал силы; вызываем по необходимости)
python -m src.cli media --profile software --resume

# Stage 3: глубокое досье через Perplexity (дорого, ограничивай limit; используй --resume чтобы пропускать уже заполненные строки)
python -m src.cli dossier --profile software --limit 10
```

## Колонки результата

**Общие**
- `company_name`, `website`, `profile`, `updated_stages`, `last_updated`
- `baseline_summary`, `insight_bullet`
- `has_software`, `software_products`, `business_model`, `market_focus`, `is_relevant`

**ISO/MSP профиль**
- `category`, `services`, `merchant_segments`, `partnerships`

**Stage 2 (сигналы)**
- `news_highlight`, `article_highlight`, `linkedin_highlight`, `signal_confidence`

**Stage 3 (досье)**
- `dossier_summary`, `dossier_wins`, `dossier_setbacks`, `dossier_regulatory`, `dossier_workforce`, `dossier_quotes`, `dossier_sources`, `dossier_error`