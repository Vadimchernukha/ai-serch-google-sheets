from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import sleep
from typing import Any, Dict, List

import httpx
from loguru import logger

from config import Settings
from sources.api_clients import ExternalArticle, LinkedInPost, SerpResult
from sources.web_scraper import SiteData
from utils.text import (
    CompanyRecord,
    collect_candidate_products,
    detect_keywords,
    filter_software_candidates,
    truncate_text,
)


@dataclass
class LLMEnrichment:
    summary: str
    insights: str
    has_software: bool = False
    software_products: List[str] = field(default_factory=list)
    business_model: str = "other"
    market_focus: str = "OTHER"
    category: str = "NO"
    iso_services: List[str] = field(default_factory=list)
    merchant_segments: List[str] = field(default_factory=list)
    partnerships: List[str] = field(default_factory=list)
    # Enterprise-specific fields
    industry: str = "Unknown"
    has_exclusion: bool = False
    exclusion_reason: str = ""
    tech_signals: List[str] = field(default_factory=list)
    raw_response: Dict[str, Any] | None = None


@dataclass
class DossierPayload:
    summary: str
    wins: List[str]
    setbacks: List[str]
    workforce_changes: List[str]
    regulatory: List[str]
    notable_quotes: List[str]
    sources: List[str]


def build_summary_and_insights(
    profile: str,
    company: CompanyRecord,
    site_data: SiteData,
    serp_data: SerpResult,
    news: List[ExternalArticle],
    linkedin_posts: List[LinkedInPost],
    settings: Settings,
) -> LLMEnrichment:
    context = _build_context_payload(site_data, serp_data, news, linkedin_posts)

    if settings.openai_api_key:
        try:
            return _call_openai(profile, company, context, settings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI request failed, falling back to heuristics: {}", exc)

    if settings.perplexity_api_key:
        try:
            return _call_perplexity(profile, company, context, settings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Perplexity request failed, using heuristics: {}", exc)

    return _heuristic_fallback(profile, context)


def _call_openai(
    profile: str, company: CompanyRecord, context: Dict[str, Any], settings: Settings
) -> LLMEnrichment:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = _format_prompt(profile, company, context)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": "You are a research assistant that produces JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    return _parse_llm_json(profile, content, raise_on_error=True)


def _invoke_perplexity(
    messages: List[Dict[str, str]],
    settings: Settings,
    *,
    temperature: float = 0.2,
    search_mode: str | None = None,
) -> Dict[str, Any]:
    if not settings.perplexity_api_key:
        raise ValueError("PERPLEXITY_API_KEY is not configured")

    headers = {
        "Authorization": f"Bearer {settings.perplexity_api_key}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": settings.perplexity_model,
        "messages": messages,
        "temperature": temperature,
    }
    if search_mode:
        payload["search_mode"] = search_mode

    with httpx.Client(timeout=settings.http_timeout) as client:
        response = client.post("https://api.perplexity.ai/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


def _call_perplexity(
    profile: str, company: CompanyRecord, context: Dict[str, Any], settings: Settings
) -> LLMEnrichment:
    prompt = _format_prompt(profile, company, context)
    data = _invoke_perplexity(
        [
            {"role": "system", "content": "You are a research assistant that produces JSON only."},
            {"role": "user", "content": prompt},
        ],
        settings,
        temperature=0.2,
    )
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    return _parse_llm_json(profile, content, raise_on_error=True)


def _heuristic_fallback(profile: str, context: Dict[str, Any]) -> LLMEnrichment:
    if profile == "iso_msp":
        return _heuristic_iso_payload(context)

    texts = [context.get("site_text", ""), context.get("serp_overview", "")]
    news_text = " ".join(article.get("title", "") for article in context.get("news", []))
    posts_text = " ".join(post.get("text", "") for post in context.get("linkedin_posts", []))
    texts.extend([news_text, posts_text])

    combined = " ".join(filter(None, texts)).strip()
    summary = truncate_text(combined or "No data gathered.", 500)

    keywords = ["launch", "partnership", "funding", "growth"]
    insights_present = detect_keywords([news_text], keywords)
    insights = "Key headlines indicate momentum." if insights_present else "Limited public signals detected."

    products = collect_candidate_products([context.get("site_text", ""), posts_text])
    software_products = filter_software_candidates(products)
    has_software = bool(software_products)
    business_model = "other"
    market_focus = "OTHER"

    return LLMEnrichment(
        summary=summary,
        insights=insights,
        has_software=has_software,
        software_products=software_products[:5],
        business_model=business_model,
        market_focus=market_focus,
    )


def _heuristic_iso_payload(context: Dict[str, Any]) -> LLMEnrichment:
    text = context.get("site_text", "").lower()
    summary = truncate_text(context.get("site_text", ""), 400)
    insights = "Limited structured data detected."

    if any(keyword in text for keyword in ("payment processor", "card processor", "merchant processor", "processing network")):
        category = "Payment Processor"
    elif any(keyword in text for keyword in ("payment gateway", "gateway provider")):
        category = "Payment Gateway"
    elif "service provider" in text or "psp" in text:
        category = "Payment Service Provider"
    elif "independent sales" in text or "iso" in text:
        category = "ISO/MSP"
    elif "acquirer" in text or "acquiring" in text or "merchant acquirer" in text:
        category = "Acquirer"
    else:
        category = "NO"

    service_keywords = {
        "payment processing": "Payment processing",
        "gateway": "Payment gateway",
        "pos": "POS systems",
        "terminal": "Hardware/terminals",
        "fraud": "Fraud/Risk management",
        "merchant account": "Merchant account setup",
        "settlement": "Settlement & funding",
        "acquiring": "Acquiring services",
        "chargeback": "Chargeback management",
    }
    services: List[str] = []
    for keyword, label in service_keywords.items():
        if keyword in text and label not in services:
            services.append(label)

    merchant_segments: List[str] = []
    for keyword in ("retail", "restaurant", "ecommerce", "healthcare", "hospitality", "nonprofit", "education"):
        if keyword in text:
            merchant_segments.append(keyword.capitalize())

    partnerships: List[str] = []
    for keyword in ("visa", "mastercard", "american express", "discover", "stripe", "adyen", "fis", "fiserv", "global payments"):
        if keyword in text and keyword.title() not in partnerships:
            partnerships.append(keyword.title())

    has_software = any(term in text for term in ("portal", "platform", "software", "saas", "dashboard"))
    software_products = []

    return LLMEnrichment(
        summary=summary or "Summary unavailable.",
        insights=insights,
        has_software=has_software,
        software_products=software_products,
        business_model="service",
        market_focus="B2B",
        category=category,
        iso_services=services,
        merchant_segments=merchant_segments,
        partnerships=partnerships,
    )


def _build_context_payload(
    site_data: SiteData,
    serp_data: SerpResult,
    news: List[ExternalArticle],
    linkedin_posts: List[LinkedInPost],
) -> Dict[str, Any]:
    return {
        "site_text": site_data.combined_text(),
        "serp_overview": serp_data.overview,
        "serp_articles": [article.as_dict() for article in serp_data.articles],
        "news": [article.as_dict() for article in news],
        "linkedin_posts": [post.as_dict() for post in linkedin_posts],
    }


def build_company_dossier(company: CompanyRecord, settings: Settings, *, horizon_months: int = 18) -> DossierPayload:
    identifier = company.name or company.domain or "Unknown company"
    user_prompt = (
        f"Company: {identifier}\n"
        f"Focus on material events within the last {horizon_months} months.\n"
        "Return strict JSON with keys: summary (string), wins (array of strings), setbacks (array of strings), "
        "workforce_changes (array of strings), regulatory (array of strings), notable_quotes (array of strings), "
        "sources (array of URLs). For each array include concise bullet-level items. Include at least one source when possible."
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are an analyst generating risk/opportunity dossiers. Respond with valid JSON only. "
                "Cite trustworthy sources and prefer verifiable facts."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            data = _invoke_perplexity(messages, settings, temperature=0.0, search_mode="web")
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            return _parse_dossier_json(content)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            wait_time = 1.5 * (attempt + 1)
            logger.warning(
                "Perplexity dossier attempt {} failed for {} ({}). Retrying in {:.1f}s",
                attempt + 1,
                identifier,
                exc,
                wait_time,
            )
            sleep(wait_time)

    raise RuntimeError(f"Perplexity dossier failed after retries for {identifier}") from last_error


def _parse_dossier_json(content: str) -> DossierPayload:
    stripped = content.strip()
    if stripped.startswith("```"):
        parts = stripped.splitlines()
        if parts and parts[0].startswith("```"):
            parts = parts[1:]
        while parts and parts[-1].startswith("```"):
            parts = parts[:-1]
        stripped = "\n".join(parts).strip()
        content = stripped or content
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.debug("Dossier payload is not valid JSON: {}", content)
        data = {}

    def _as_list(key: str) -> List[str]:
        value = data.get(key) or []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    summary = str(data.get("summary") or "No dossier insights found.").strip()
    wins = _as_list("wins")
    setbacks = _as_list("setbacks")
    workforce = _as_list("workforce_changes")
    regulatory = _as_list("regulatory")
    notable_quotes = _as_list("notable_quotes")
    sources = _as_list("sources")

    if summary == "No dossier insights found." and not any([wins, setbacks, workforce, regulatory, notable_quotes, sources]):
        logger.warning("Perplexity dossier returned empty payload: {}", content)

    return DossierPayload(
        summary=summary,
        wins=wins,
        setbacks=setbacks,
        workforce_changes=workforce,
        regulatory=regulatory,
        notable_quotes=notable_quotes,
        sources=sources,
    )


def _format_prompt(profile: str, company: CompanyRecord, context: Dict[str, Any]) -> str:
    if profile == "iso_msp":
        return (
            f"Company: {company.name}\n"
            "Return strict JSON with keys: summary (string), insights (string), iso_category (one of [Payment Gateway, Payment Processor, Payment Service Provider, ISO/MSP, Hybrid, Other]), services (array of strings), merchant_segments (array of strings), geography (string), partnerships (array of strings), offers_software (bool), software_products (array of strings).\n"
            "Use provided material only.\n"
            f"Website content:\n{truncate_text(context.get('site_text', ''), 4000)}\n\n"
            f"Search overview:\n{truncate_text(context.get('serp_overview', ''), 1500)}\n\n"
            f"Articles:\n{truncate_text(json.dumps(context.get('serp_articles', [])[:5], ensure_ascii=False), 1500)}\n\n"
            f"News:\n{truncate_text(json.dumps(context.get('news', [])[:5], ensure_ascii=False), 1500)}\n\n"
            f"LinkedIn posts:\n{truncate_text(json.dumps(context.get('linkedin_posts', [])[:5], ensure_ascii=False), 1500)}"
        )

    if profile == "enterprise":
        return (
            f"Company: {company.name}\n"
            "Return strict JSON with keys: summary (string), insights (string), industry (string), "
            "has_exclusion (bool - true if company is: IT service provider/outsourcing/custom software/IT consulting, e-commerce store/marketplace, video game developer, non-profit/religious organization, military/space organization), "
            "exclusion_reason (string - reason if has_exclusion is true, empty otherwise), "
            "tech_signals (array of strings - look for: digital transformation, automation, data analytics, logistics technology, developer/data scientist jobs, complex data-heavy industries like manufacturing/healthcare/supply chain/energy/transportation, client/partner/supplier portals, own tools/apps/platforms, innovation/R&D initiatives, technology infrastructure), "
            "has_software (bool - true if company develops own software/tools/platforms, not just uses third-party software), "
            "software_products (array of strings - list of proprietary software/tools/platforms if has_software is true), "
            "business_model (enum one of [product, service, platform, marketplace, hybrid, other]), "
            "market_focus (enum one of [B2B, B2C, B2B2C, B2G, Mixed, Other]).\n"
            "Use provided material only.\n"
            f"Website content:\n{truncate_text(context.get('site_text', ''), 4000)}\n\n"
            f"Search overview:\n{truncate_text(context.get('serp_overview', ''), 1500)}\n\n"
            f"Articles:\n{truncate_text(json.dumps(context.get('serp_articles', [])[:5], ensure_ascii=False), 1500)}\n\n"
            f"News:\n{truncate_text(json.dumps(context.get('news', [])[:5], ensure_ascii=False), 1500)}\n\n"
            f"LinkedIn posts:\n{truncate_text(json.dumps(context.get('linkedin_posts', [])[:5], ensure_ascii=False), 1500)}"
        )

    return (
        f"Company: {company.name}\n"
        "Return strict JSON with keys: summary (string), insights (string), has_software (bool), software_products (array of strings containing only software/SaaS/platform offerings), business_model (enum one of [product, service, platform, marketplace, hybrid, other]), market_focus (enum one of [B2B, B2C, B2B2C, B2G, Mixed, Other]).\n"
        "Use provided material only.\n"
        f"Website content:\n{truncate_text(context.get('site_text', ''), 4000)}\n\n"
        f"Search overview:\n{truncate_text(context.get('serp_overview', ''), 1500)}\n\n"
        f"Articles:\n{truncate_text(json.dumps(context.get('serp_articles', [])[:5], ensure_ascii=False), 1500)}\n\n"
        f"News:\n{truncate_text(json.dumps(context.get('news', [])[:5], ensure_ascii=False), 1500)}\n\n"
        f"LinkedIn posts:\n{truncate_text(json.dumps(context.get('linkedin_posts', [])[:5], ensure_ascii=False), 1500)}"
    )


def _parse_llm_json(profile: str, content: str, *, raise_on_error: bool = False) -> LLMEnrichment:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.debug("LLM did not return valid JSON, content={}", content)
        if raise_on_error:
            raise ValueError("LLM response is not valid JSON") from exc
        data = {}

    summary = data.get("summary") or "Summary unavailable."
    insights = data.get("insights") or "No insights returned."

    if profile == "iso_msp":
        raw_category = data.get("category") or data.get("iso_category") or "NO"
        services = data.get("services") or []
        if not isinstance(services, list):
            services = [str(services)]
        category = _normalize_iso_category(raw_category)
        if category == "NO" and services:
            category = _normalize_iso_category(" ".join(services))
        merchant_segments = data.get("merchant_segments") or data.get("target_merchants") or []
        if not isinstance(merchant_segments, list):
            merchant_segments = [str(merchant_segments)]
        software_products = data.get("software_products") or []
        if not isinstance(software_products, list):
            software_products = [str(software_products)]
        software_products = filter_software_candidates(software_products)
        has_software = bool(data.get("has_software") or data.get("offers_software") or software_products)

        business_model = data.get("business_model") or "service"
        market_focus = data.get("market_focus") or "B2B"

        return LLMEnrichment(
            summary=summary,
            insights=insights,
            has_software=has_software,
            software_products=[str(item) for item in software_products][:8],
            business_model=str(business_model).lower(),
            market_focus=str(market_focus).upper(),
            category=category,
            iso_services=[str(item) for item in services][:8],
            merchant_segments=[str(item) for item in merchant_segments][:8],
            partnerships=[str(item) for item in data.get("partnerships", [])][:8],
            raw_response=data,
        )

    if profile == "enterprise":
        industry = data.get("industry") or "Unknown"
        has_exclusion = bool(data.get("has_exclusion"))
        exclusion_reason = data.get("exclusion_reason") or ""
        tech_signals = data.get("tech_signals") or []
        if not isinstance(tech_signals, list):
            tech_signals = [str(tech_signals)]
        
        software_products = data.get("software_products") or []
        if not isinstance(software_products, list):
            software_products = [str(software_products)]
        software_products = filter_software_candidates(software_products)
        has_software = bool(data.get("has_software") or software_products)
        
        business_model = data.get("business_model") or "other"
        market_focus = data.get("market_focus") or "Other"
        
        allowed_models = {"product", "service", "platform", "marketplace", "hybrid", "other"}
        bm_normalized = str(business_model).lower()
        business_model = bm_normalized if bm_normalized in allowed_models else "other"
        
        allowed_markets = {"B2B", "B2C", "B2B2C", "B2G", "MIXED", "OTHER"}
        mf_normalized = str(market_focus).upper()
        market_focus = mf_normalized if mf_normalized in allowed_markets else "OTHER"
        
        return LLMEnrichment(
            summary=summary,
            insights=insights,
            has_software=has_software,
            software_products=[str(item) for item in software_products][:8],
            business_model=business_model,
            market_focus=market_focus,
            industry=str(industry),
            has_exclusion=has_exclusion,
            exclusion_reason=str(exclusion_reason),
            tech_signals=[str(item) for item in tech_signals][:10],
            raw_response=data,
        )

    software_products = data.get("software_products") or data.get("product_names") or []
    if not isinstance(software_products, list):
        software_products = [str(software_products)]
    software_products = filter_software_candidates(software_products)
    has_software = bool(data.get("has_software") or data.get("has_products") or software_products)
    business_model = data.get("business_model") or "other"
    market_focus = data.get("market_focus") or "Other"

    allowed_models = {"product", "service", "platform", "marketplace", "hybrid", "other"}
    bm_normalized = str(business_model).lower()
    business_model = bm_normalized if bm_normalized in allowed_models else "other"

    allowed_markets = {"B2B", "B2C", "B2B2C", "B2G", "MIXED", "OTHER"}
    mf_normalized = str(market_focus).upper()
    market_focus = mf_normalized if mf_normalized in allowed_markets else "OTHER"

    return LLMEnrichment(
        summary=summary,
        insights=insights,
        has_software=has_software,
        software_products=[str(item) for item in software_products][:8],
        business_model=business_model,
        market_focus=market_focus,
        raw_response=data,
    )


def _normalize_iso_category(raw: Any) -> str:
    if not isinstance(raw, str):
        return "NO"
    value = raw.strip().lower()
    if value in {"", "none", "no", "n/a", "na", "null"}:
        return "NO"
    mapping = {
        "processor": "Payment Processor",
        "payment processor": "Payment Processor",
        "card processor": "Payment Processor",
        "merchant processor": "Payment Processor",
        "processing network": "Payment Processor",
        "issuing processor": "Payment Processor",
        "payment gateway": "Payment Gateway",
        "gateway": "Payment Gateway",
        "gateway provider": "Payment Gateway",
        "checkout": "Payment Gateway",
        "payment service provider": "Payment Service Provider",
        "psp": "Payment Service Provider",
        "merchant service provider": "Payment Service Provider",
        "payment solution provider": "Payment Service Provider",
        "iso": "ISO/MSP",
        "msp": "ISO/MSP",
        "iso/msp": "ISO/MSP",
        "independent sales organization": "ISO/MSP",
        "independent sales organisations": "ISO/MSP",
        "acquirer": "Acquirer",
        "merchant acquirer": "Acquirer",
        "acquiring": "Acquirer",
        "hybrid": "Hybrid",
        "aggregator": "Payment Gateway",
    }
    if value in mapping:
        return mapping[value]
    for key, label in mapping.items():
        if key in value:
            return label
    return value.upper() if value in {"payment gateway", "payment processor", "payment service provider", "iso/msp", "acquirer", "hybrid"} else "NO"

