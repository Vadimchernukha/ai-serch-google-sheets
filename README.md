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

## Streamlit Dashboard

Визуализация данных через веб-интерфейс:

```bash
streamlit run src/dashboard.py
```

### Деплой на Streamlit Cloud

1. Перейди на [share.streamlit.io](https://share.streamlit.io)
2. Подключи GitHub репозиторий `Vadimchernukha/ai-serch-google-sheets`
3. Укажи:
   - **Main file path:** `src/dashboard.py`
   - **Python version:** 3.11 (или выше)
4. Добавь секреты (Secrets) в Streamlit Cloud (Manage app → Secrets):
   ```toml
   GOOGLE_SERVICE_ACCOUNT_JSON = '{"type": "service_account", "project_id": "...", "private_key_id": "...", "private_key": "...", "client_email": "...", "client_id": "...", "auth_uri": "...", "token_uri": "...", "auth_provider_x509_cert_url": "...", "client_x509_cert_url": "..."}'
   GSHEET_ID = "твой_id_таблицы"
   GSHEET_WORKSHEET_SOFTWARE = "Software"
   GSHEET_WORKSHEET_ISO_MSP = "ISO/MSP"
   ```
   **Важно:** `GOOGLE_SERVICE_ACCOUNT_JSON` должен быть строкой JSON в одинарных кавычках (весь JSON в одной строке).
5. Нажми Deploy

Дашборд будет доступен по публичному URL.

## Колонки результата

**Общие**
- `company_name`, `website`, `profile`, `updated_stages`, `last_updated`
- `baseline_summary`, `insight_bullet`
- `has_software`, `software_products`, `business_model`, `market_focus`, `is_relevant`

**ISO/MSP профиль**
- `category`, `services`, `merchant_segments`, `partnerships`

**Stage 2 (сигналы)**
- `news_highlight`, `article_highlight`, `linkedin_highlight`, `signal_confidence`

**Stage 3 (досье)**
- `dossier_summary`, `dossier_wins`, `dossier_setbacks`, `dossier_regulatory`, `dossier_workforce`, `dossier_quotes`, `dossier_sources`, `dossier_error`