#!/usr/bin/env python3
"""
Утилита для преобразования Google Service Account JSON в формат для Streamlit Cloud Secrets.

Использование:
1. Сохрани свой Google Service Account JSON файл (например, credentials.json)
2. Запусти: python convert_json_for_streamlit.py credentials.json
3. Скопируй вывод и вставь в Streamlit Cloud Secrets
"""

import json
import sys
from pathlib import Path


def convert_json_to_toml_format(json_file_path: str) -> str:
    """Преобразует JSON файл в формат для TOML secrets."""
    path = Path(json_file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {json_file_path}")
    
    # Читаем JSON
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Преобразуем в одну строку с правильным экранированием
    json_string = json.dumps(data, ensure_ascii=False)
    
    # Создаем TOML формат
    toml_output = f"""GOOGLE_SERVICE_ACCOUNT_JSON = '{json_string}'

GSHEET_URL = "https://docs.google.com/spreadsheets/d/твой-id-таблицы/edit"
GSHEET_WORKSHEET_SOFTWARE = "Software"
GSHEET_WORKSHEET_ISO_MSP = "ISO/MSP"
"""
    
    return toml_output


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python convert_json_for_streamlit.py <путь_к_json_файлу>")
        print("\nПример:")
        print("  python convert_json_for_streamlit.py credentials.json")
        sys.exit(1)
    
    json_file = sys.argv[1]
    
    try:
        output = convert_json_to_toml_format(json_file)
        print("=" * 80)
        print("СКОПИРУЙ ЭТО И ВСТАВЬ В STREAMLIT CLOUD SECRETS:")
        print("=" * 80)
        print()
        print(output)
        print("=" * 80)
        print("\n✅ Готово! Скопируй весь текст выше и вставь в Streamlit Cloud → Secrets")
    except Exception as e:
        print(f"❌ Ошибка: {e}", file=sys.stderr)
        sys.exit(1)

