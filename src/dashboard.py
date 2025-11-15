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
        
        # Debug: log what we're receiving (only in debug mode)
        debug_info = []
        
        # Process all secrets
        for key, value in secrets.items():
            key_upper = key.upper()
            
            if key_upper == "GOOGLE_SERVICE_ACCOUNT_JSON":
                # Handle JSON specially - it might be a dict or a string
                if isinstance(value, dict):
                    # If it's already a dict, serialize it to JSON string
                    os.environ[key_upper] = json.dumps(value)
                    debug_info.append(f"Set {key_upper} from dict")
                elif isinstance(value, str):
                    # If it's a string, validate it's valid JSON and use as-is
                    try:
                        json.loads(value)
                        os.environ[key_upper] = value
                        debug_info.append(f"Set {key_upper} from string")
                    except (json.JSONDecodeError, TypeError):
                        os.environ[key_upper] = value
                        debug_info.append(f"Set {key_upper} from string (invalid JSON)")
                else:
                    os.environ[key_upper] = str(value)
                    debug_info.append(f"Set {key_upper} from other type")
            elif isinstance(value, dict):
                # Flatten nested dicts (for other nested secrets)
                for nested_key, nested_value in value.items():
                    env_key = f"{key_upper}_{nested_key.upper()}"
                    os.environ[env_key] = str(nested_value)
                    debug_info.append(f"Set {env_key} from nested dict")
            else:
                # Simple string values - set directly
                os.environ[key_upper] = str(value)
                debug_info.append(f"Set {key_upper} = {str(value)[:50]}...")
        
        # Debug: show what keys we received
        received_keys = list(secrets.keys())
        
        # Check if GSHEET_ID or GSHEET_URL was set
        if "GSHEET_ID" not in os.environ and "GSHEET_URL" not in os.environ:
            st.error("⚠️ **GSHEET_ID или GSHEET_URL не найден в секретах!**")
            st.warning(f"**Полученные ключи из секретов:** {', '.join(received_keys)}")
            
            with st.expander("📋 Инструкция по настройке секретов"):
                st.markdown("""
                **Проблема:** `GSHEET_ID` или `GSHEET_URL` не найден в секретах Streamlit Cloud.
                
                **Решение:**
                1. Перейди в Streamlit Cloud → **Manage app** → **Secrets**
                2. Добавь **один из вариантов** ниже:
                """)
                st.code("""
[GOOGLE_SERVICE_ACCOUNT_JSON]
type = "service_account"
project_id = "твой-project-id"
private_key_id = "твой-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
client_email = "твой-email@project.iam.gserviceaccount.com"
client_id = "твой-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."

# Вариант 1: только ID таблицы
GSHEET_ID = "твой-id-таблицы"

# Вариант 2: полная ссылка (можно использовать вместо GSHEET_ID)
# GSHEET_URL = "https://docs.google.com/spreadsheets/d/твой-id-таблицы/edit"

GSHEET_WORKSHEET_SOFTWARE = "Software"
GSHEET_WORKSHEET_ISO_MSP = "ISO/MSP"
                """, language="toml")
                st.markdown("""
                **Важно:**
                - Используй **либо** `GSHEET_ID` **либо** `GSHEET_URL` (не оба сразу)
                - Если используешь `GSHEET_URL` - просто скопируй полную ссылку на таблицу
                - Ключи должны быть **ВНЕ** секции `[GOOGLE_SERVICE_ACCOUNT_JSON]`
                - Не используй отступы перед этими ключами
                """)
            
            # Show what we actually received
            with st.expander("🔍 Отладочная информация"):
                st.json({k: str(type(v).__name__) for k, v in secrets.items()})
    
    return Settings()


def load_companies(profile: str) -> List[Dict[str, Any]]:
    """Load companies from Google Sheet for the given profile."""
    try:
        settings = load_settings_from_streamlit()
        sheet = SheetClient(settings, worksheet_name=settings.worksheet_for_profile(profile))
        rows = sheet.fetch_rows()
        return rows
    except Exception as exc:
        st.error(f"Failed to load data: {exc}")
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

