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
        # Set environment variables from Streamlit secrets
        for key, value in secrets.items():
            if key == "GOOGLE_SERVICE_ACCOUNT_JSON":
                # Handle JSON specially - it might be a dict or a string
                if isinstance(value, dict):
                    # If it's already a dict, serialize it to JSON string
                    os.environ[key] = json.dumps(value)
                elif isinstance(value, str):
                    # If it's a string, validate it's valid JSON and use as-is
                    try:
                        # Validate JSON by parsing it
                        json.loads(value)
                        os.environ[key] = value
                    except (json.JSONDecodeError, TypeError):
                        # If invalid, try to escape and use as-is
                        os.environ[key] = value
                else:
                    os.environ[key] = str(value)
            elif isinstance(value, dict):
                # Flatten nested dicts (for other nested secrets)
                for nested_key, nested_value in value.items():
                    env_key = f"{key}_{nested_key}".upper()
                    os.environ[env_key] = str(nested_value)
            else:
                # Simple string values
                os.environ[key] = str(value)
    
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
    relevance_filter = st.sidebar.selectbox(
        "Relevance",
        ["All", "Relevant", "Not Relevant", "Pending"],
    )
    
    has_software_filter = st.sidebar.selectbox(
        "Has Software",
        ["All", "Yes", "No"],
    )
    
    # Apply filters
    filtered_companies = companies
    if relevance_filter == "Relevant":
        filtered_companies = [c for c in filtered_companies if c.get("is_relevant") == "True" or c.get("is_relevant") is True]
    elif relevance_filter == "Not Relevant":
        filtered_companies = [c for c in filtered_companies if c.get("is_relevant") == "False" or c.get("is_relevant") is False]
    elif relevance_filter == "Pending":
        filtered_companies = [c for c in filtered_companies if c.get("is_relevant") not in ("True", "False", True, False) or c.get("is_relevant") == ""]
    
    if has_software_filter == "Yes":
        filtered_companies = [c for c in filtered_companies if c.get("has_software") == "True" or c.get("has_software") is True]
    elif has_software_filter == "No":
        filtered_companies = [c for c in filtered_companies if c.get("has_software") == "False" or c.get("has_software") is False]
    
    st.sidebar.metric("Total Companies", len(filtered_companies))
    
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
    
    # Company selection
    company_names = [
        f"{c.get('company_name') or c.get('website') or 'Unknown'} ({c.get('website', 'N/A')})"
        for c in filtered_companies
    ]
    
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

