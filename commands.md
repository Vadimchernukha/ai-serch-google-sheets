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

4. Первый запуск попросит выбрать профиль и режим:
   - `1` — software: текущая логика (summary/insights/софт, extended = новости)
   - `2` — iso_msp: компании-обработчики платежей, отдельные поля для категорий ISO/PSP
   После профиля: выбор режима `basic` или `extended` (новости, статьи, LinkedIn)

5. Примеры команд
   - `1` — basic: только summary/insights/products
   - `2` — extended: плюс новости, статьи, LinkedIn посты

6. Полный прогон (с пропуском уже заполненных строк)
   ```bash
   python -m src.main --profile software --resume
   python -m src.main --profile iso_msp --mode extended --resume
   ```

### Полезные опции

- `WORKER_COUNT` в `.env` — число параллельных потоков (по умолчанию 3).
- `ENABLE_PLAYWRIGHT=0` — отключить тяжёлый fallback на браузер.
- `HTTP_TIMEOUT` — таймаут HTTP-запросов в секундах.


