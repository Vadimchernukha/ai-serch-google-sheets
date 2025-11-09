from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger

from config import Settings
from nlp.llm import (
    DossierPayload,
    LLMEnrichment,
    build_company_dossier,
    build_summary_and_insights,
)
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


def collect_profile(row: Dict[str, Any], settings: Settings, profile: str, index: int = 0) -> Dict[str, Any]:
    company = normalize_company(row, index=index)
    logger.info("[{}] {}", index + 1, company.name or company.domain or "Unknown")

    site_data = _safe_scrape(company, settings)
    serp_data = fetch_serp_overview(company, settings)

    news_items: List[ExternalArticle] = []
    linkedin_posts: List[LinkedInPost] = []

    llm_payload = build_summary_and_insights(
        profile,
        company,
        site_data,
        serp_data,
        news_items,
        linkedin_posts,
        settings,
    )

    has_software, software_products = _merge_software_signals(
        site_data,
        serp_data,
        news_items,
        linkedin_posts,
        llm_payload,
    )

    result: Dict[str, Any] = {**row}
    result["profile"] = profile
    result["baseline_summary"] = llm_payload.summary
    result["insight_bullet"] = llm_payload.insights
    result["has_software"] = has_software
    result["software_products"] = ", ".join(software_products[:8])
    result["business_model"] = llm_payload.business_model
    result["market_focus"] = llm_payload.market_focus

    if profile != "software":
        result["category"] = llm_payload.category
        result["services"] = ", ".join(llm_payload.iso_services[:8])
        result["merchant_segments"] = ", ".join(llm_payload.merchant_segments[:8])
        result["partnerships"] = ", ".join(llm_payload.partnerships[:8])
    else:
        # ensure ISO-specific columns are cleared if switching profile
        for field in ("category", "services", "merchant_segments", "partnerships"):
            if field in result:
                result[field] = ""

    result["is_relevant"] = _evaluate_relevance(profile, llm_payload, has_software)
    result.setdefault("dossier_summary", "")
    result.setdefault("dossier_wins", "")
    result.setdefault("dossier_setbacks", "")
    result.setdefault("dossier_regulatory", "")
    result.setdefault("dossier_workforce", "")
    result.setdefault("dossier_quotes", "")
    result.setdefault("dossier_sources", "")
    result.setdefault("dossier_error", "")

    result["updated_stages"] = _mark_stage(row.get("updated_stages"), "1")
    result["last_updated"] = _now_utc()

    obsolete_fields = [
        "summary",
        "insights",
        "latest_news",
        "articles",
        "linkedin_posts",
        "profile_refreshed_at",
        "media_refreshed_at",
        "dossier_refreshed_at",
    ]
    for field in obsolete_fields:
        result.pop(field, None)

    return result


def collect_media(row: Dict[str, Any], settings: Settings, profile: str, index: int = 0) -> Dict[str, Any]:
    company = normalize_company(row, index=index)
    logger.info("[{}] {} (media)", index + 1, company.name or company.domain or "Unknown")

    serp_data = fetch_serp_overview(company, settings)
    news_items = fetch_news_articles(company, settings)
    linkedin_posts = fetch_linkedin_posts(company, settings)

    news_raw = [article.as_dict() for article in news_items[:5]]
    serp_raw = [article.as_dict() for article in serp_data.articles[:5]]
    linkedin_raw = [
        post.as_dict() for post in linkedin_posts[: settings.linkedin_posts_limit]
    ]

    news_highlight = _highlight_from_articles(news_items)
    article_highlight = _highlight_from_articles(serp_data.articles)
    linkedin_highlight = _highlight_from_posts(linkedin_posts)

    signal_confidence = min(
        100,
        (len(news_items) + len(serp_data.articles) + len(linkedin_posts)) * 15,
    )

    result = {
        **row,
        "news_highlight": news_highlight,
        "article_highlight": article_highlight,
        "linkedin_highlight": linkedin_highlight,
        "signal_confidence": signal_confidence,
        "_news_raw": news_raw,
        "_articles_raw": serp_raw,
        "_linkedin_raw": linkedin_raw,
    }

    if profile == "software" and not row.get("has_software"):
        # Update software signals if new articles hint at products
        llm_payload = LLMEnrichment(
            summary=row.get("baseline_summary", ""),
            insights=row.get("insight_bullet", ""),
            has_software=row.get("has_software", False),
            software_products=[item.strip() for item in (row.get("software_products") or "").split(",") if item.strip()],
            business_model=row.get("business_model", "other"),
            market_focus=row.get("market_focus", "OTHER"),
        )
        candidates = filter_software_candidates(
            collect_candidate_products(article.get("summary", "") for article in news_raw if article.get("summary"))
        )
        merged = sorted(set(llm_payload.software_products + candidates))
        result["software_products"] = ", ".join(merged[:10])
        result["has_software"] = bool(merged)

    result["updated_stages"] = _mark_stage(row.get("updated_stages"), "2")
    result["last_updated"] = _now_utc()

    for field in ("articles", "latest_news", "linkedin_posts", "media_refreshed_at"):
        result.pop(field, None)

    return result


def collect_dossier(row: Dict[str, Any], settings: Settings, index: int = 0) -> Dict[str, Any]:
    company = normalize_company(row, index=index)
    logger.info("[{}] {} (dossier)", index + 1, company.name or company.domain or "Unknown")

    error_note = ""
    try:
        payload: DossierPayload = build_company_dossier(company, settings)
    except Exception as exc:  # noqa: BLE001
        logger.opt(exception=exc).error(
            "Dossier generation failed for {}",
            company.name or company.domain or "Unknown",
        )
        error_note = str(exc)
        fallback_summary = "Dossier unavailable."
        if error_note:
            fallback_summary = f"{fallback_summary} Reason: {error_note}"
        payload = DossierPayload(
            summary=fallback_summary[:500],
            wins=[],
            setbacks=[],
            workforce_changes=[],
            regulatory=[],
            notable_quotes=[],
            sources=[],
        )

    def _format(items: List[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else ""

    result = {
        **row,
        "dossier_summary": payload.summary,
        "dossier_wins": _format(payload.wins),
        "dossier_setbacks": _format(payload.setbacks),
        "dossier_workforce": _format(payload.workforce_changes),
        "dossier_regulatory": _format(payload.regulatory),
        "dossier_quotes": _format(payload.notable_quotes),
        "dossier_sources": "; ".join(payload.sources),
        "dossier_error": error_note[:500],
    }

    if (
        payload.summary == "No dossier insights found."
        and not any([payload.wins, payload.setbacks, payload.workforce_changes, payload.regulatory, payload.notable_quotes])
    ):
        heuristic = _heuristic_dossier_from_row(row, error_note)
        result.update(heuristic)

    result["updated_stages"] = _mark_stage(row.get("updated_stages"), "3")
    result["last_updated"] = _now_utc()

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


def _mark_stage(marker: Optional[Any], stage: str) -> str:
    stages: set[str] = set()
    if marker:
        if isinstance(marker, (list, tuple, set)):
            iterable = marker
        else:
            iterable = str(marker).split(",")
        for item in iterable:
            value = str(item).strip()
            if value:
                stages.add(value)
    stages.add(stage)

    def _sort_key(value: str) -> tuple[int, str]:
        return (int(value), value) if value.isdigit() else (99, value)

    ordered = sorted(stages, key=_sort_key)
    return ",".join(ordered)


def _highlight_from_articles(articles: Iterable[ExternalArticle]) -> str:
    lines: List[str] = []
    for article in list(articles)[:3]:
        title = getattr(article, "title", None)
        summary = getattr(article, "summary", None)
        source = getattr(article, "source", None)
        published_at = getattr(article, "published_at", None)
        url = getattr(article, "url", None)

        parts: List[str] = []
        if published_at:
            parts.append(str(published_at))
        if title:
            parts.append(str(title))
        if source:
            parts.append(f"({source})")
        if summary:
            parts.append(str(summary))

        line = " — ".join(part for part in parts if part)
        if url:
            line = f"{line} ⇒ {url}" if line else str(url)
        if line:
            lines.append(f"- {line}")
    return "\n".join(lines)


def _highlight_from_posts(posts: Iterable[LinkedInPost]) -> str:
    lines: List[str] = []
    for post in list(posts)[:3]:
        text = getattr(post, "text", None)
        url = getattr(post, "url", None)
        published_at = getattr(post, "published_at", None)
        parts = []
        if published_at:
            parts.append(str(published_at))
        if text:
            parts.append(str(text))
        line = " — ".join(parts)
        if url:
            line = f"{line} ⇒ {url}" if line else str(url)
        if line:
            lines.append(f"- {line}")
    return "\n".join(lines)


def _split_highlight(text: str) -> List[str]:
    if not text:
        return []
    items: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            stripped = stripped[2:]
        if stripped:
            items.append(stripped)
    return items


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


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _heuristic_dossier_from_row(row: Dict[str, Any], error_note: str) -> Dict[str, Any]:
    summary_parts: List[str] = []
    base_summary = row.get("baseline_summary") or row.get("summary")
    if base_summary:
        summary_parts.append(base_summary)
    insights = row.get("insight_bullet") or row.get("insights")
    if insights and insights not in summary_parts:
        summary_parts.append(f"Insights: {insights}")
    heuristic_summary = "\n".join(summary_parts) if summary_parts else "Limited public data; refer to summary/insights."

    def _parse_items(raw: Any) -> List[Dict[str, Any]]:
        if not raw:
            return []
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [item for item in parsed if isinstance(item, dict)]
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(text)
                    if isinstance(parsed, list):
                        return [item for item in parsed if isinstance(item, dict)]
                except (ValueError, SyntaxError):
                    return []
        return []

    news_items = _parse_items(row.get("_news_raw")) or _parse_items(row.get("latest_news"))
    article_items = _parse_items(row.get("_articles_raw")) or _parse_items(row.get("articles"))
    linkedin_items = _parse_items(row.get("_linkedin_raw")) or _parse_items(row.get("linkedin_posts"))

    if not news_items and row.get("news_highlight"):
        news_items = [{"summary": item} for item in _split_highlight(row["news_highlight"])]
    if not article_items and row.get("article_highlight"):
        article_items = [{"summary": item} for item in _split_highlight(row["article_highlight"])]
    if not linkedin_items and row.get("linkedin_highlight"):
        linkedin_items = [{"summary": item} for item in _split_highlight(row["linkedin_highlight"])]

    negative_keywords = {"layoff", "lawsuit", "loss", "decline", "fine", "penalty", "investigation", "breach", "fraud", "shutdown", "bankruptcy"}
    positive_keywords = {"launch", "growth", "expansion", "partnership", "award", "acquired", "record", "milestone", "investment", "raised", "integration"}
    workforce_positive = {"hiring", "recruit", "expanding headcount", "new office", "expansion", "opens"}
    workforce_negative = {"layoff", "cut", "reduce headcount", "restructuring", "downsizing"}
    regulatory_keywords = {"regulator", "regulation", "compliance", "fine", "penalty", "lawsuit", "investigation", "settlement", "sec"}

    wins: List[str] = []
    setbacks: List[str] = []
    workforce: List[str] = []
    regulatory: List[str] = []
    quotes: List[str] = []

    def _classify(item: Dict[str, Any]) -> None:
        text = " ".join(
            str(part)
            for part in [
                item.get("title"),
                item.get("summary"),
                item.get("text"),
                item.get("snippet"),
                item.get("description"),
            ]
            if part
        )
        if not text:
            return
        lower = text.lower()
        bullet = text.strip()
        if any(keyword in lower for keyword in workforce_positive):
            workforce.append(bullet)
        if any(keyword in lower for keyword in workforce_negative):
            workforce.append(bullet)
            setbacks.append(bullet)
            return
        if any(keyword in lower for keyword in regulatory_keywords):
            regulatory.append(bullet)
        if any(keyword in lower for keyword in negative_keywords):
            setbacks.append(bullet)
        elif any(keyword in lower for keyword in positive_keywords):
            wins.append(bullet)
        else:
            wins.append(bullet)

        quote = item.get("quote") or item.get("text")
        if quote:
            quotes.append(str(quote).strip())

    for collection in (news_items, article_items, linkedin_items):
        for entry in collection[:6]:
            _classify(entry)

    # Deduplicate while preserving order
    def _dedupe(seq: List[str]) -> List[str]:
        seen = set()
        unique: List[str] = []
        for item in seq:
            key = item.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(key)
        return unique

    wins = _dedupe(wins)[:6]
    setbacks = _dedupe(setbacks)[:6]
    workforce = _dedupe(workforce)[:6]
    regulatory = _dedupe(regulatory)[:6]
    quotes = _dedupe(quotes)[:6]

    if not wins and (row.get("insight_bullet") or row.get("insights")):
        wins.append(str(row.get("insight_bullet") or row.get("insights")))

    fallback_error = error_note or "Perplexity returned empty payload; populated via heuristic signals."

    return {
        "dossier_summary": heuristic_summary[:500],
        "dossier_wins": "\n".join(f"- {item}" for item in wins) if wins else "",
        "dossier_setbacks": "\n".join(f"- {item}" for item in setbacks) if setbacks else "",
        "dossier_workforce": "\n".join(f"- {item}" for item in workforce) if workforce else "",
        "dossier_regulatory": "\n".join(f"- {item}" for item in regulatory) if regulatory else "",
        "dossier_quotes": "\n".join(f"- {item}" for item in quotes) if quotes else "",
        "dossier_sources": "",
        "dossier_error": fallback_error[:500],
    }

