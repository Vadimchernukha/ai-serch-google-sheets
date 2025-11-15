"""Streamlit dashboard for visualizing enriched company data."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from loguru import logger

# Add project root to path for imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import Settings
from src.google_sheet import SheetClient


def load_settings_from_streamlit() -> Settings:
    """Load settings from Streamlit secrets or environment variables."""
    import json
    
    # Check if running on Streamlit Cloud
    if hasattr(st, "secrets") and st.secrets:
        secrets = st.secrets
        
        # Обрабатываем секреты
        for key, value in secrets.items():
            key_upper = key.upper()
            
            if key_upper == "GOOGLE_SERVICE_ACCOUNT_JSON":
                # Специальная обработка для GOOGLE_SERVICE_ACCOUNT_JSON
                if isinstance(value, dict):
                    # Если это словарь (из TOML секции), сериализуем в JSON
                    os.environ[key_upper] = json.dumps(value)
                elif isinstance(value, str):
                    # Если это строка, проверяем валидность
                    try:
                        parsed = json.loads(value)
                        if not isinstance(parsed, dict) or "type" not in parsed:
                            st.warning(f"⚠️ GOOGLE_SERVICE_ACCOUNT_JSON не содержит валидный service account JSON")
                        os.environ[key_upper] = value
                    except json.JSONDecodeError as exc:
                        st.error(f"⚠️ **Ошибка в GOOGLE_SERVICE_ACCOUNT_JSON:** Невалидный JSON: {exc}")
                        os.environ[key_upper] = value
            elif isinstance(value, dict):
                # Другие словари - просто сериализуем
                os.environ[key_upper] = json.dumps(value)
            elif isinstance(value, str):
                # Простые строки
                os.environ[key_upper] = value
            else:
                # Остальные типы
                os.environ[key_upper] = str(value)
        
        # Проверка что необходимые ключи установлены
        received_keys = [k.upper() for k in secrets.keys()]
        required_keys = ["GSHEET_ID", "GSHEET_URL"]
        has_required = any(key in received_keys for key in required_keys)
        
        if not has_required:
            st.error("⚠️ **GSHEET_ID или GSHEET_URL не найден в секретах!**")
            st.warning(f"**Полученные ключи:** {', '.join(received_keys)}")
            
            with st.expander("📋 Инструкция по настройке секретов"):
                st.markdown("""
                **Проблема:** `GSHEET_ID` или `GSHEET_URL` не найден в секретах Streamlit Cloud.
                
                **Решение:**
                1. Перейди в Streamlit Cloud → **Manage app** → **Secrets**
                2. Добавь секреты в формате:
                """)
                st.code("""
GOOGLE_SERVICE_ACCOUNT_JSON = '{"type":"service_account","project_id":"...","private_key":"...","client_email":"..."}'

GSHEET_URL = "https://docs.google.com/spreadsheets/d/твой-id/edit"
GSHEET_WORKSHEET_SOFTWARE = "Software"
GSHEET_WORKSHEET_ISO_MSP = "ISO/MSP"
                """, language="toml")
                st.markdown("""
                **Важно:**
                - `GOOGLE_SERVICE_ACCOUNT_JSON` должен быть **JSON строкой в одну строку** внутри одинарных кавычек
                - `GSHEET_URL` - полная ссылка на таблицу (или используй `GSHEET_ID` с ID таблицы)
                - Все ключи должны быть на верхнем уровне (не внутри секций)
                """)
            
            # Show what we actually received
            with st.expander("🔍 Отладочная информация"):
                st.json({k: str(type(v).__name__) for k, v in secrets.items()})
    
    # Settings автоматически загрузит переменные из os.environ
    return Settings()


def load_companies(profile: str) -> List[Dict[str, Any]]:
    """Load companies from Google Sheet for the given profile."""
    try:
        settings = load_settings_from_streamlit()
        
        # Попробуем загрузить service account info для проверки
        try:
            sa_info = settings.service_account_info()
            if "private_key" not in sa_info:
                st.error("⚠️ **В JSON отсутствует поле 'private_key'**")
            elif not sa_info.get("private_key", "").startswith("-----BEGIN PRIVATE KEY-----"):
                st.warning("⚠️ **private_key не начинается с '-----BEGIN PRIVATE KEY-----'**")
                st.info("Возможно, переносы строк неправильно экранированы в TOML")
        except Exception as sa_exc:
            error_msg = str(sa_exc)
            if "Invalid JWT Signature" in error_msg or "invalid_grant" in error_msg:
                st.error("⚠️ **Ошибка аутентификации: Invalid JWT Signature**")
                st.markdown("""
                **Возможные причины:**
                1. **Переносы строк в private_key** - в TOML они должны быть как `\\n` (два символа: обратный слэш и n)
                2. **JSON поврежден** - проверь что весь JSON в одну строку
                3. **Кавычки** - используй одинарные кавычки для всей JSON строки
                
                **Правильный формат в TOML:**
                ```toml
                GOOGLE_SERVICE_ACCOUNT_JSON = '{"private_key":"-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBgkqhkiG...\\n-----END PRIVATE KEY-----\\n",...}'
                ```
                
                **Важно:** `\\n` в TOML означает один символ новой строки в JSON, не реальный перенос строки!
                """)
            else:
                st.error(f"⚠️ **Ошибка при загрузке credentials:** {error_msg}")
        
        sheet = SheetClient(settings, worksheet_name=settings.worksheet_for_profile(profile))
        rows = sheet.fetch_rows()
        return rows
    except Exception as exc:
        error_msg = str(exc)
        st.error(f"Failed to load data: {error_msg}")
        
        # Дополнительная диагностика для JWT ошибок
        if "Invalid JWT Signature" in error_msg or "invalid_grant" in error_msg:
            with st.expander("🔧 Как исправить ошибку JWT Signature"):
                st.markdown("""
                **Проблема:** Google не может проверить подпись JWT токена.
                
                **Решение:**
                1. Открой свой Google Service Account JSON файл
                2. Скопируй **весь файл целиком** (Ctrl+A, Ctrl+C)
                3. В Streamlit Cloud Secrets вставь его в одну строку:
                
                ```toml
                GOOGLE_SERVICE_ACCOUNT_JSON = '{"type":"service_account","project_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n",...}'
                ```
                
                **Критически важно:**
                - JSON должен быть в **одну строку** (без реальных переносов)
                - Переносы строк в `private_key` должны быть как `\\n` (два символа)
                - Используй **одинарные кавычки** вокруг всей JSON строки
                - Не добавляй пробелы или переносы внутри JSON
                """)
        
        logger.exception("Failed to load companies")
        return []


def format_field(value: Any, default: str = "—") -> str:
    """Format a field value for display."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return "✅ Yes" if value else "❌ No"
    if isinstance(value, str):
        return value.strip()
    return str(value)


def render_company_detail(company: Dict[str, Any], profile: str) -> None:
    """Render detailed view of a company."""
    st.header(company.get("company_name") or company.get("website") or "Unknown Company")
    
    # Basic info
    col1, col2, col3 = st.columns(3)
    with col1:
        website = company.get("website", "")
        if website:
            st.markdown(f"**Website:** [{website}](https://{website})")
        else:
            st.markdown("**Website:** —")
    
    with col2:
        profile_val = company.get("profile", profile)
        st.markdown(f"**Profile:** {profile_val}")
    
    with col3:
        is_relevant = company.get("is_relevant", "")
        if is_relevant == "True" or is_relevant is True:
            st.markdown("**Relevance:** ✅ Relevant")
        elif is_relevant == "False" or is_relevant is False:
            st.markdown("**Relevance:** ❌ Not Relevant")
        else:
            st.markdown("**Relevance:** ⏳ Pending")
    
    st.divider()
    
    # Summary and Insights
    summary = format_field(company.get("baseline_summary"))
    if summary != "—":
        st.subheader("📋 Summary")
        st.write(summary)
    
    insights = format_field(company.get("insight_bullet"))
    if insights != "—":
        st.subheader("💡 Key Insights")
        # Split bullet points if they're separated by newlines or commas
        insight_list = [i.strip() for i in insights.replace("•", "").split("\n") if i.strip()]
        if not insight_list:
            insight_list = [i.strip() for i in insights.split(",") if i.strip()]
        if insight_list:
            for insight in insight_list:
                st.markdown(f"- {insight}")
        else:
            st.write(insights)
    
    st.divider()
    
    # Business Model & Market Focus
    col1, col2 = st.columns(2)
    with col1:
        business_model = format_field(company.get("business_model"))
        if business_model != "—":
            st.markdown(f"**Business Model:** {business_model}")
    
    with col2:
        market_focus = format_field(company.get("market_focus"))
        if market_focus != "—":
            st.markdown(f"**Market Focus:** {market_focus}")
    
    # Software Products
    has_software = company.get("has_software", "")
    software_products = format_field(company.get("software_products"))
    
    if has_software == "True" or has_software is True:
        st.markdown("**Has Software:** ✅ Yes")
        if software_products != "—":
            st.markdown(f"**Software Products:** {software_products}")
    elif has_software == "False" or has_software is False:
        st.markdown("**Has Software:** ❌ No")
    
    # ISO/MSP specific fields
    if profile == "iso_msp":
        st.divider()
        st.subheader("🏢 ISO/MSP Details")
        
        category = format_field(company.get("category"))
        if category != "—":
            st.markdown(f"**Category:** {category}")
        
        services = format_field(company.get("services"))
        if services != "—":
            st.markdown(f"**Services:** {services}")
        
        merchant_segments = format_field(company.get("merchant_segments"))
        if merchant_segments != "—":
            st.markdown(f"**Merchant Segments:** {merchant_segments}")
        
        partnerships = format_field(company.get("partnerships"))
        if partnerships != "—":
            st.markdown(f"**Partnerships:** {partnerships}")
    
    # Stage 2: Media & Signals
    st.divider()
    st.subheader("📰 Media & Signals")
    
    news_highlight = format_field(company.get("news_highlight"))
    if news_highlight != "—":
        st.markdown("**Latest News:**")
        st.write(news_highlight)
    
    article_highlight = format_field(company.get("article_highlight"))
    if article_highlight != "—":
        st.markdown("**Article Highlights:**")
        st.write(article_highlight)
    
    linkedin_highlight = format_field(company.get("linkedin_highlight"))
    if linkedin_highlight != "—":
        st.markdown("**LinkedIn Highlights:**")
        st.write(linkedin_highlight)
    
    signal_confidence = format_field(company.get("signal_confidence"))
    if signal_confidence != "—":
        st.markdown(f"**Signal Confidence:** {signal_confidence}")
    
    # Stage 3: Deep Dive Dossier
    dossier_summary = format_field(company.get("dossier_summary"))
    if dossier_summary != "—":
        st.divider()
        st.subheader("🔍 Deep Dive Dossier")
        st.write(dossier_summary)
        
        dossier_wins = format_field(company.get("dossier_wins"))
        if dossier_wins != "—":
            st.markdown("**Wins:**")
            st.write(dossier_wins)
        
        dossier_setbacks = format_field(company.get("dossier_setbacks"))
        if dossier_setbacks != "—":
            st.markdown("**Setbacks:**")
            st.write(dossier_setbacks)
        
        dossier_regulatory = format_field(company.get("dossier_regulatory"))
        if dossier_regulatory != "—":
            st.markdown("**Regulatory:**")
            st.write(dossier_regulatory)
        
        dossier_workforce = format_field(company.get("dossier_workforce"))
        if dossier_workforce != "—":
            st.markdown("**Workforce:**")
            st.write(dossier_workforce)
        
        dossier_quotes = format_field(company.get("dossier_quotes"))
        if dossier_quotes != "—":
            st.markdown("**Key Quotes:**")
            st.write(dossier_quotes)
        
        dossier_sources = format_field(company.get("dossier_sources"))
        if dossier_sources != "—":
            st.markdown("**Sources:**")
            st.write(dossier_sources)
        
        dossier_error = format_field(company.get("dossier_error"))
        if dossier_error != "—":
            st.error(f"Dossier Error: {dossier_error}")
    
    # Metadata
    st.divider()
    with st.expander("📊 Metadata"):
        col1, col2 = st.columns(2)
        with col1:
            updated_stages = format_field(company.get("updated_stages"))
            st.markdown(f"**Updated Stages:** {updated_stages}")
        with col2:
            last_updated = format_field(company.get("last_updated"))
            st.markdown(f"**Last Updated:** {last_updated}")


def main() -> None:
    """Main Streamlit app."""
    st.set_page_config(
        page_title="Company Research Dashboard",
        page_icon="🏢",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    st.title("🏢 Company Research Dashboard")
    st.markdown("Visualize enriched company data from Google Sheets")
    
    # Sidebar filters
    st.sidebar.header("Filters")
    profile = st.sidebar.selectbox(
        "Profile",
        ["software", "iso_msp"],
        format_func=lambda x: "Software" if x == "software" else "ISO/MSP",
    )
    
    # Load companies
    with st.spinner("Loading companies..."):
        companies = load_companies(profile)
    
    if not companies:
        st.warning("No companies found. Make sure your Google Sheet is configured correctly.")
        return
    
    # Filter options
    st.sidebar.subheader("🔍 Filters")
    
    # Relevance filter with quick buttons
    st.sidebar.markdown("**Filter by Relevance:**")
    relevance_options = {
        "All": "All",
        "✅ Relevant": "Relevant",
        "❌ Not Relevant": "Not Relevant",
        "⏳ Pending": "Pending",
    }
    relevance_filter = st.sidebar.radio(
        "Relevance",
        options=list(relevance_options.keys()),
        format_func=lambda x: x,
        index=0,
    )
    relevance_filter_value = relevance_options[relevance_filter]
    
    has_software_filter = st.sidebar.selectbox(
        "Has Software",
        ["All", "Yes", "No"],
    )
    
    # Apply filters
    filtered_companies = companies
    if relevance_filter_value == "Relevant":
        filtered_companies = [c for c in filtered_companies if c.get("is_relevant") == "True" or c.get("is_relevant") is True]
    elif relevance_filter_value == "Not Relevant":
        filtered_companies = [c for c in filtered_companies if c.get("is_relevant") == "False" or c.get("is_relevant") is False]
    elif relevance_filter_value == "Pending":
        filtered_companies = [c for c in filtered_companies if c.get("is_relevant") not in ("True", "False", True, False) or c.get("is_relevant") == ""]
    
    if has_software_filter == "Yes":
        filtered_companies = [c for c in filtered_companies if c.get("has_software") == "True" or c.get("has_software") is True]
    elif has_software_filter == "No":
        filtered_companies = [c for c in filtered_companies if c.get("has_software") == "False" or c.get("has_software") is False]
    
    # Statistics
    st.sidebar.divider()
    st.sidebar.metric("Total Companies", len(filtered_companies))
    relevant_count = sum(1 for c in companies if c.get("is_relevant") == "True" or c.get("is_relevant") is True)
    st.sidebar.metric("✅ Relevant", relevant_count)
    not_relevant_count = sum(1 for c in companies if c.get("is_relevant") == "False" or c.get("is_relevant") is False)
    st.sidebar.metric("❌ Not Relevant", not_relevant_count)
    
    # Company list
    if not filtered_companies:
        st.info("No companies match the selected filters.")
        return
    
    # Search box
    search_query = st.text_input("🔍 Search companies", placeholder="Search by name or website...")
    if search_query:
        search_lower = search_query.lower()
        filtered_companies = [
            c for c in filtered_companies
            if search_lower in (c.get("company_name") or "").lower()
            or search_lower in (c.get("website") or "").lower()
        ]
    
    # Company selection with relevance indicators
    def format_company_name(company: Dict[str, Any]) -> str:
        """Format company name with relevance indicator."""
        name = company.get('company_name') or company.get('website') or 'Unknown'
        website = company.get('website', 'N/A')
        
        # Add relevance indicator
        is_relevant = company.get("is_relevant")
        if is_relevant == "True" or is_relevant is True:
            indicator = "✅"
        elif is_relevant == "False" or is_relevant is False:
            indicator = "❌"
        else:
            indicator = "⏳"
        
        return f"{indicator} {name} ({website})"
    
    company_names = [format_company_name(c) for c in filtered_companies]
    
    selected_index = st.selectbox(
        "Select a company",
        range(len(company_names)),
        format_func=lambda i: company_names[i],
    )
    
    if selected_index is not None and selected_index < len(filtered_companies):
        selected_company = filtered_companies[selected_index]
        render_company_detail(selected_company, profile)
    else:
        st.info("Select a company from the dropdown above to view details.")


if __name__ == "__main__":
    main()

