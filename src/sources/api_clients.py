from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import httpx
from loguru import logger
from urllib.parse import urlparse

from config import Settings
from utils.text import CompanyRecord


@dataclass
class ExternalArticle:
    title: str
    url: str
    source: str
    published_at: Optional[str] = None
    summary: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at,
            "summary": self.summary,
        }


@dataclass
class LinkedInPost:
    title: str
    text: str
    url: str
    author: Optional[str] = None
    published_at: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "text": self.text,
            "url": self.url,
            "author": self.author,
            "published_at": self.published_at,
        }


@dataclass
class SerpResult:
    overview: str
    articles: List[ExternalArticle]


def fetch_serp_overview(company: CompanyRecord, settings: Settings) -> SerpResult:
    if not settings.serpapi_key:
        return SerpResult(overview="", articles=[])

    params = {
        "engine": "google",
        "q": f"{company.name} company overview",
        "hl": "en",
        "gl": "us",
        "api_key": settings.serpapi_key,
        "num": 5,
    }

    articles: List[ExternalArticle] = []
    overview = ""

    try:
        with httpx.Client(timeout=settings.http_timeout) as client:
            response = client.get("https://serpapi.com/search", params=params)
            response.raise_for_status()
            payload = response.json()

            overview = payload.get("knowledge_graph", {}).get("description") or ""
            if not overview and payload.get("organic_results"):
                overview = payload["organic_results"][0].get("snippet", "")

            articles.extend(_parse_serp_articles(payload.get("news_results")))

            if not articles:
                news_params = {
                    "engine": "google_news",
                    "q": f"{company.name} OR {company.domain}" if company.domain else company.name,
                    "api_key": settings.serpapi_key,
                    "gl": "us",
                    "hl": "en",
                    "num": 5,
                }
                news_resp = client.get("https://serpapi.com/search", params=news_params)
                news_resp.raise_for_status()
                news_payload = news_resp.json()
                fallback_items = news_payload.get("articles") or news_payload.get("news_results")
                articles.extend(_parse_serp_articles(fallback_items))

    except httpx.HTTPError as exc:  # noqa: BLE001
        logger.warning("SerpAPI request failed: {}", exc)
        return SerpResult(overview="", articles=[])

    return SerpResult(overview=overview, articles=articles[:5])


def _parse_serp_articles(raw_items: Optional[List[dict]]) -> List[ExternalArticle]:
    articles: List[ExternalArticle] = []
    if not raw_items:
        return articles

    for item in raw_items:
        title = item.get("title") or item.get("news_title") or ""
        link = item.get("link") or item.get("url") or ""
        if not title or not link:
            continue
        articles.append(
            ExternalArticle(
                title=title,
                url=link,
                source=item.get("source") or item.get("publisher", {}).get("name", ""),
                published_at=item.get("date") or item.get("published_date") or item.get("time_ago"),
                summary=item.get("snippet") or item.get("excerpt"),
            )
        )
    return articles


def _extract_linkedin_slug(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    parts = [segment for segment in parsed.path.strip("/").split("/") if segment]
    for segment in reversed(parts):
        if segment.lower() not in {"company", "posts", "update"}:
            return segment.lower()
    return None


def _is_relevant_linkedin_post(item: dict, company: CompanyRecord, slug: Optional[str]) -> bool:
    source = (item.get("source_company") or "").lower()
    author = (item.get("author") or {}).get("name", "").lower()
    text = (item.get("text") or "").lower()

    candidates = set()
    if slug:
        candidates.add(slug)
    if company.name:
        candidates.add(company.name.lower())
    if company.domain:
        candidates.add(company.domain.lower().split(".")[0])

    for token in list(candidates):
        if len(token) > 4 and token.endswith(".com"):
            candidates.add(token[:-4])

    return any(
        token and (token in source or token in author or token in text)
        for token in candidates
    )


def fetch_news_articles(company: CompanyRecord, settings: Settings) -> List[ExternalArticle]:
    if not settings.newsapi_key:
        return []

    params = {
        "q": f"\"{company.name}\"",
        "language": "en",
        "pageSize": 10,
        "sortBy": "publishedAt",
        "apiKey": settings.newsapi_key,
    }

    try:
        with httpx.Client(timeout=settings.http_timeout) as client:
            response = client.get("https://newsapi.org/v2/everything", params=params)
            response.raise_for_status()
    except httpx.HTTPError as exc:  # noqa: BLE001
        logger.warning("NewsAPI request failed: {}", exc)
        return []

    payload = response.json()
    articles: List[ExternalArticle] = []
    for article in payload.get("articles", [])[:10]:
        articles.append(
            ExternalArticle(
                title=article.get("title", ""),
                url=article.get("url", ""),
                source=(article.get("source") or {}).get("name", ""),
                published_at=article.get("publishedAt"),
                summary=article.get("description"),
            )
        )

    return articles


def fetch_linkedin_posts(company: CompanyRecord, settings: Settings) -> List[LinkedInPost]:
    if not settings.apify_api_token:
        return []

    linkedin_url = (company.raw.get("linkedin") or "").strip()
    if not linkedin_url:
        return []
    slug = _extract_linkedin_slug(linkedin_url)

    params = {
        "token": settings.apify_api_token,
        "waitForFinish": 120,
    }
    payload = {
        "linkedinCompanyUrls": [linkedin_url],
        "maxItems": max(settings.linkedin_posts_limit, 1),
    }

    try:
        with httpx.Client(timeout=settings.http_timeout) as client:
            run_resp = client.post(
                "https://api.apify.com/v2/acts/apimaestro~linkedin-company-posts/runs",
                params=params,
                json=payload,
            )
            run_resp.raise_for_status()
            run_data = run_resp.json().get("data", {})
            dataset_id = run_data.get("defaultDatasetId")
            if not dataset_id:
                return []

            dataset_resp = client.get(
                f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                params={"token": settings.apify_api_token, "clean": "1"},
            )
            dataset_resp.raise_for_status()
            items = dataset_resp.json()
    except httpx.HTTPError as exc:  # noqa: BLE001
        logger.warning("Apify LinkedIn request failed: {}", exc)
        return []

    posts: List[LinkedInPost] = []
    seen_urls: set[str] = set()
    for item in items[: settings.linkedin_posts_limit]:
        if not _is_relevant_linkedin_post(item, company, slug):
            continue
        text = item.get("text", "")
        title = item.get("title") or (text[:97] + "..." if len(text) > 100 else text)
        url = item.get("url") or item.get("link", "") or item.get("post_url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        posts.append(
            LinkedInPost(
                title=title or "LinkedIn Post",
                text=text,
                url=url,
                author=(item.get("author") or {}).get("name") or item.get("profileName"),
                published_at=item.get("publishedAt")
                or (item.get("posted_at") or {}).get("date")
                or item.get("timeAgo"),
            )
        )

    return posts

