from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from utils.text import CompanyRecord


@dataclass
class PageSnapshot:
    url: str
    title: str
    text: str


@dataclass
class SiteData:
    pages: List[PageSnapshot]

    def combined_text(self, max_chars: int = 8000) -> str:
        payload = "\n\n".join(page.text for page in self.pages if page.text)
        return payload[:max_chars]


_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
_SUFFIXES = ["", "about", "solutions", "products", "platform", "news"]
_MAX_PAGES = 6


def scrape_site(company: CompanyRecord, settings) -> SiteData:
    logger.debug("Scraping candidate urls for {}", company.name)
    candidates = company.generate_candidate_urls()
    if not candidates:
        return SiteData(pages=[])

    pages: List[PageSnapshot] = []
    urls: List[str] = []
    seen: set[str] = set()

    for base_url in candidates[:2]:
        for suffix in _SUFFIXES:
            target = _join_url(base_url, suffix)
            if target in seen:
                continue
            seen.add(target)
            urls.append(target)

    http_results = _run_async(_fetch_many_http(urls, settings.http_timeout))
    for target in urls:
        html = http_results.get(target)
        if not html:
            continue
        snapshot = _html_to_snapshot(target, html)
        if snapshot:
            pages.append(snapshot)
        if len(pages) >= _MAX_PAGES:
            break

    if pages or not settings.enable_playwright:
        return SiteData(pages=pages[:_MAX_PAGES])

    try:
        html = _fetch_with_playwright(candidates[0], settings.http_timeout)
        snapshot = _html_to_snapshot(candidates[0], html)
        if snapshot:
            pages.append(snapshot)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Playwright fallback failed for {}: {}", candidates[0], exc)

    return SiteData(pages=pages[:_MAX_PAGES])


def _html_to_snapshot(url: str, html: str) -> Optional[PageSnapshot]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    text = soup.get_text(separator=" ", strip=True)
    if not text:
        return None
    return PageSnapshot(url=url, title=title, text=text)


async def _fetch_many_http(urls: List[str], timeout: float) -> Dict[str, Optional[str]]:
    if not urls:
        return {}

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=_HTTP_HEADERS) as client:
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    result: Dict[str, Optional[str]] = {}
    for url, response in zip(urls, responses):
        if isinstance(response, Exception):
            logger.debug("HTTP fetch failed for {}: {}", url, response)
            result[url] = None
            continue
        try:
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.debug("HTTP fetch failed for {}: {}", url, exc)
            result[url] = None
            continue
        result[url] = response.text
    return result


def _fetch_with_playwright(url: str, timeout: float) -> str:
    async def runner() -> str:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            html = await page.content()
            await browser.close()
            return html

    return _run_async(runner())


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
    except RuntimeError:
        pass

    return asyncio.run(coro)


def _join_url(base: str, suffix: str) -> str:
    if not suffix:
        return base.rstrip("/")
    return f"{base.rstrip('/')}/{suffix}"

