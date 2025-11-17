"""Streamlit dashboard for visualizing enriched company data."""

from __future__ import annotations

from typing import Any, Dict, List

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials
from loguru import logger


@st.cache_resource
def get_gspread_client():
    """Create and cache gspread client from Streamlit secrets."""
    try:
        # Получаем credentials напрямую из secrets
        google_creds_dict = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
        
        # Создаем credentials
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        credentials = Credentials.from_service_account_info(
            google_creds_dict,
            scopes=scopes
        )
        
        # Авторизуемся в gspread
        client = gspread.authorize(credentials)
        return client
    except Exception as exc:
        st.error(f"⚠️ **Ошибка при создании Google Sheets клиента:** {exc}")
        logger.exception("Failed to create gspread client")
        return None


def load_companies(profile: str) -> List[Dict[str, Any]]:
    """Load companies from Google Sheet for the given profile."""
    try:
        # Получаем gspread клиент
        client = get_gspread_client()
        if not client:
            return []
        
        # Открываем таблицу
        sheet = client.open_by_url(st.secrets["GSHEET_URL"])
        
        # Определяем имя worksheet
        if profile == "software":
            worksheet_name = st.secrets.get("GSHEET_WORKSHEET_SOFTWARE", "Software")
        elif profile == "iso_msp":
            worksheet_name = st.secrets.get("GSHEET_WORKSHEET_ISO_MSP", "ISO/MSP")
        elif profile == "enterprise":
            worksheet_name = st.secrets.get("GSHEET_WORKSHEET_ENTERPRISE", "Enterprise")
        else:
            worksheet_name = "Sheet1"
        
        # Получаем worksheet
        try:
            worksheet = sheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # Пробуем альтернативные имена
            alt_names = ["Software", "ISO/MSP", "Enterprise", "Sheet1"]
            worksheet = None
            for name in alt_names:
                try:
                    worksheet = sheet.worksheet(name)
                    break
                except gspread.exceptions.WorksheetNotFound:
                    continue
            
            if not worksheet:
                st.error(f"⚠️ Worksheet '{worksheet_name}' не найден в таблице")
                return []
        
        # Получаем все данные
        all_values = worksheet.get_all_values()
        if not all_values:
            return []
        
        # Первая строка - заголовки
        headers = all_values[0]
        
        # Преобразуем в список словарей
        companies = []
        for row_idx, row_values in enumerate(all_values[1:], start=2):
            company = {}
            for col_idx, header in enumerate(headers):
                value = row_values[col_idx] if col_idx < len(row_values) else ""
                company[header] = value
            company["__row"] = row_idx
            companies.append(company)
        
        logger.info(f"Loaded {len(companies)} companies from Google Sheet")
        return companies
        
    except Exception as exc:
        error_msg = str(exc)
        st.error(f"Failed to load data: {error_msg}")
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
    
    profile_options = {
        "software": "Software",
        "iso_msp": "ISO/MSP",
        "enterprise": "Enterprise"
    }
    
    profile = st.sidebar.selectbox(
        "Profile",
        list(profile_options.keys()),
        format_func=lambda x: profile_options[x],
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

