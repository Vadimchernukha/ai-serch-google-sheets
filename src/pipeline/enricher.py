from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger

from config import Settings
from nlp.llm import LLMEnrichment, build_summary_and_insights
from sources.api_clients import (
    ExternalArticle,
    LinkedInPost,
    SerpResult,
    fetch_linkedin_posts,
    fetch_news_articles,
    fetch_serp_overview,
)
from sources.web_scraper import SiteData, scrape_site
from utils.text import (
    CompanyRecord,
    collect_candidate_products,
    filter_software_candidates,
    normalize_company,
)


def enrich_company(
    row: Dict[str, Any],
    settings: Settings,
    profile: str,
    mode: str,
    index: int = 0,
) -> Dict[str, Any]:
    company = normalize_company(row, index=index)
    logger.info("[{}] {}", index + 1, company.name or company.domain or "Unknown")

    site_data = _safe_scrape(company, settings)
    serp_data = fetch_serp_overview(company, settings)
    include_extended = mode == "extended"
    news_items = fetch_news_articles(company, settings) if include_extended else []
    linkedin_posts = fetch_linkedin_posts(company, settings) if include_extended else []

    llm_payload = build_summary_and_insights(
        profile,
        company,
        site_data,
        serp_data,
        news_items,
        linkedin_posts,
        settings,
    )

    if profile == "software":
        has_software, software_products = _merge_software_signals(
            site_data,
            serp_data,
            news_items,
            linkedin_posts,
            llm_payload,
        )
    else:
        has_software = llm_payload.has_software
        software_products = llm_payload.software_products

    result: Dict[str, Any] = {
        **row,
        "summary": llm_payload.summary,
        "insights": llm_payload.insights,
    }

    if profile == "software":
        result.update(
            {
                "has_software": has_software,
                "software_products": ", ".join(software_products[:10]),
                "business_model": llm_payload.business_model,
                "market_focus": llm_payload.market_focus,
            }
        )
    else:
        result.update(
            {
                "has_software": has_software,
                "software_products": ", ".join(software_products[:10]),
                "category": llm_payload.category,
                "services": ", ".join(llm_payload.iso_services[:10]),
                "merchant_segments": ", ".join(llm_payload.merchant_segments[:10]),
                "partnerships": ", ".join(llm_payload.partnerships[:10]),
                "business_model": llm_payload.business_model,
                "market_focus": llm_payload.market_focus,
            }
        )

    result["is_relevant"] = _evaluate_relevance(profile, llm_payload, has_software)

    if include_extended:
        result.update(
            {
                "latest_news": [article.as_dict() for article in news_items[:5]],
                "articles": [article.as_dict() for article in serp_data.articles[:5]],
                "linkedin_posts": [
                    post.as_dict() for post in linkedin_posts[: settings.linkedin_posts_limit]
                ],
            }
        )
    else:
        result.setdefault("latest_news", [])
        result.setdefault("articles", [])
        result.setdefault("linkedin_posts", [])

    return result


def _safe_scrape(company: CompanyRecord, settings: Settings) -> SiteData:
    try:
        data = scrape_site(company, settings)
        if not data.pages:
            logger.debug("No pages scraped for {}", company.name)
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scraping failed for {}: {}", company.name, exc)
        return SiteData(pages=[])


def _merge_software_signals(
    site_data: SiteData,
    serp_data: SerpResult,
    news: List[ExternalArticle],
    linkedin_posts: List[LinkedInPost],
    llm_payload: LLMEnrichment,
) -> tuple[bool, List[str]]:
    heuristics = filter_software_candidates(collect_candidate_products(page.text for page in site_data.pages))
    news_candidates = filter_software_candidates(collect_candidate_products(article.summary or "" for article in news))
    post_candidates = filter_software_candidates(collect_candidate_products(post.text for post in linkedin_posts))

    candidates = set(str(name) for name in llm_payload.software_products)
    for source in (heuristics, news_candidates, post_candidates):
        for item in source:
            candidates.add(item)

    software_list = [item for item in candidates if item]
    software_list.sort()

    return (llm_payload.has_software or bool(software_list)), software_list


def _evaluate_relevance(profile: str, payload: LLMEnrichment, has_software: bool) -> bool:
    if profile == "software":
        if not has_software:
            return False
        if payload.business_model not in {"product", "platform", "hybrid"}:
            return False
        if payload.market_focus not in {"B2B", "B2B2C", "B2G"}:
            return False
        return True

    if payload.category not in {
        "Payment Processor",
        "Payment Service Provider",
        "ISO/MSP",
        "Acquirer",
        "Hybrid",
    }:
        return False

    if not has_software:
        return False

    services_text = " ".join(payload.iso_services).lower()
    return any(keyword in services_text for keyword in ("processing", "merchant", "gateway", "pos", "risk", "settlement", "acquiring", "chargeback"))

