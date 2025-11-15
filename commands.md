## Быстрый запуск

1. Создать и активировать окружение
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Установить зависимости
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

3. Настроить переменные окружения
   ```bash
   cp config/env.example .env
   # отредактируй .env: GOOGLE_SERVICE_ACCOUNT_FILE, GSHEET_URL/ID, листы Software и ISO/MSP, API ключи (OPENAI, NEWSAPI, SERPAPI, APIFY)
   ```

4. Теперь три отдельных этапа:
   - Stage 1 — базовый сбор и анализ (`scrape`)
   - Stage 2 — новости/LinkedIn/статьи (`media`)
   - Stage 3 — «досье» через Perplexity (`dossier`)

5. Команды
   ```bash
   # Stage 1: baseline_summary, фильтры, софт-проверка
   python -m src.cli scrape --profile software --resume

   # Stage 2: новости/статьи/LinkedIn (хайлайты без сырых массивов)
   python -m src.cli media --profile software --resume

   # Stage 3: глубокое досье (дороже, по умолчанию обновляет все строки; добавь --resume чтобы перескочить заполненные)
   python -m src.cli dossier --profile software --limit 10
   ```

6. Запуск дашборда (Streamlit)
   ```bash
   streamlit run src/dashboard.py
   ```

### Полезные опции

- `WORKER_COUNT` в `.env` — число параллельных потоков (Stage 1).
- `ENABLE_PLAYWRIGHT=0` — отключить тяжёлый fallback на браузер.
- `HTTP_TIMEOUT` — таймаут HTTP-запросов в секундах.
- `PERPLEXITY_MODEL` — модель Perplexity (по умолчанию `sonar`).


