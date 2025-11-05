from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence


@dataclass
class CompanyRecord:
    raw: Dict[str, Any]
    name: str
    domain: Optional[str]
    row_index: int

    def generate_candidate_urls(self, max_candidates: int = 4) -> List[str]:
        urls: List[str] = []
        if self.domain:
            domain = self.domain.strip()
            if domain and not domain.startswith("http"):
                urls.append(f"https://{domain}")
                urls.append(f"http://{domain}")
            elif domain:
                urls.append(domain)

        if not urls and self.name:
            slug = _slugify(self.name)
            if slug:
                urls.append(f"https://{slug}.com")

        deduped: List[str] = []
        for url in urls:
            if url not in deduped:
                deduped.append(url)
        return deduped[:max_candidates]


def normalize_company(row: Dict[str, Any], index: int = 0) -> CompanyRecord:
    name_fields = ["company", "Company", "name", "Name", "organization"]
    domain_fields = ["domain", "Domain", "website", "Website", "url"]

    name = _first_non_empty(row, name_fields) or _first_non_empty(row, domain_fields) or ""
    domain = _first_non_empty(row, domain_fields)

    return CompanyRecord(raw=row, name=name.strip(), domain=(domain or "").strip(), row_index=index)


def truncate_text(payload: str, limit: int = 4000) -> str:
    payload = payload.strip()
    if len(payload) <= limit:
        return payload
    return payload[: limit - 3].rstrip() + "..."


def detect_keywords(texts: Iterable[str], keywords: Sequence[str]) -> bool:
    normalized = [kw.lower() for kw in keywords]
    for text in texts:
        lower = text.lower()
        if any(keyword in lower for keyword in normalized):
            return True
    return False


def collect_candidate_products(texts: Iterable[str]) -> List[str]:
    candidates: List[str] = []
    pattern = re.compile(r"^[\w\-\s]{3,60}$")
    for text in texts:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.count(" ") > 7:
                continue
            if any(token in line.lower() for token in ("product", "platform", "solution", "suite")):
                if pattern.match(line) and line not in candidates:
                    candidates.append(line)
    return candidates


def filter_software_candidates(candidates: Iterable[str]) -> List[str]:
    software_keywords = (
        "software",
        "platform",
        "app",
        "application",
        "tool",
        "suite",
        "system",
        "saas",
        "cloud",
        "portal",
        "engine",
        "dashboard",
        "studio",
        "analytics",
    )
    results: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        lower = candidate.lower()
        keep = any(keyword in lower for keyword in software_keywords)
        if not keep and "service" in lower:
            if " as a service" in lower or "-as-a-service" in lower or "service platform" in lower:
                keep = True
        if keep and candidate not in seen:
            seen.add(candidate)
            results.append(candidate)
    return results


def _first_non_empty(row: Dict[str, Any], fields: Sequence[str]) -> Optional[str]:
    for field in fields:
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value.replace("-", "")

