from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")

    google_service_account_json: Optional[str] = Field(default=None, alias="GOOGLE_SERVICE_ACCOUNT_JSON")
    google_service_account_file: Optional[str] = Field(default=None, alias="GOOGLE_SERVICE_ACCOUNT_FILE")
    gsheet_id: Optional[str] = Field(default=None, alias="GSHEET_ID")
    gsheet_url: Optional[str] = Field(default=None, alias="GSHEET_URL")
    gsheet_worksheet: str = Field("Sheet1", alias="GSHEET_WORKSHEET")
    gsheet_worksheet_software: Optional[str] = Field(default=None, alias="GSHEET_WORKSHEET_SOFTWARE")
    gsheet_worksheet_iso_msp: Optional[str] = Field(default=None, alias="GSHEET_WORKSHEET_ISO_MSP")
    gsheet_worksheet_enterprise: Optional[str] = Field(default=None, alias="GSHEET_WORKSHEET_ENTERPRISE")

    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o-mini", alias="OPENAI_MODEL")
    perplexity_api_key: Optional[str] = Field(default=None, alias="PERPLEXITY_API_KEY")
    perplexity_model: str = Field("sonar", alias="PERPLEXITY_MODEL")
    serpapi_key: Optional[str] = Field(default=None, alias="SERPAPI_KEY")
    valueserp_api_key: Optional[str] = Field(default=None, alias="VALUESERP_API_KEY")
    newsapi_key: Optional[str] = Field(default=None, alias="NEWSAPI_KEY")
    apify_api_token: Optional[str] = Field(default=None, alias="APIFY_API_TOKEN")

    http_timeout: float = Field(15.0, alias="HTTP_TIMEOUT")
    max_companies: int = Field(0, alias="MAX_COMPANIES")
    enable_playwright: bool = Field(True, alias="ENABLE_PLAYWRIGHT")
    worker_count: int = Field(3, alias="WORKER_COUNT", ge=1, le=16)
    linkedin_posts_limit: int = Field(5, alias="LINKEDIN_POSTS_LIMIT", ge=1, le=20)
    report_dir: str = Field("reports", alias="REPORT_DIR")

    run_id: str = Field(default_factory=lambda: datetime.utcnow().strftime("%Y%m%d-%H%M%S"))

    def service_account_info(self) -> Dict[str, Any]:
        if self.google_service_account_file:
            path = Path(self.google_service_account_file).expanduser().resolve()
            if not path.exists():
                raise ValueError(f"Google service account file not found: {path}")
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in service account file {path}: {exc}") from exc

        if self.google_service_account_json:
            raw = self.google_service_account_json.strip()
            if raw.endswith("..."):
                raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON placeholder detected; provide real credentials or set GOOGLE_SERVICE_ACCOUNT_FILE")
        try:
                return json.loads(raw)
        except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid Google service account JSON: {exc}") from exc

        raise ValueError("Google service account credentials are not configured")

    @property
    def report_path(self) -> Path:
        return Path(self.report_dir).expanduser().resolve()

    def as_env(self) -> Dict[str, str]:
        return {
            "OPENAI_API_KEY": self.openai_api_key or "",
            "NEWSAPI_KEY": self.newsapi_key or "",
            "SERPAPI_KEY": self.serpapi_key or "",
            "PERPLEXITY_API_KEY": self.perplexity_api_key or "",
            "PERPLEXITY_MODEL": self.perplexity_model,
            "APIFY_API_TOKEN": self.apify_api_token or "",
        }

    @model_validator(mode="after")
    def ensure_gsheet_id(self) -> "Settings":
        if not self.gsheet_id and self.gsheet_url:
            extracted = _extract_sheet_id(self.gsheet_url)
            if extracted:
                object.__setattr__(self, "gsheet_id", extracted)

        if not self.gsheet_id:
            raise ValueError("GSHEET_ID or GSHEET_URL must be provided")
        return self

    def worksheet_for_profile(self, profile: str) -> List[str]:
        candidates: List[Optional[str]] = []
        if profile == "iso_msp":
            candidates.extend([self.gsheet_worksheet_iso_msp, "ISO/MSP"])
        elif profile == "enterprise":
            candidates.extend([self.gsheet_worksheet_enterprise, "Enterprise"])
        else:
            candidates.extend([self.gsheet_worksheet_software, "Software"])
        candidates.append(self.gsheet_worksheet)

        ordered: List[str] = []
        for name in candidates + ["Sheet1"]:
            if name and name not in ordered:
                ordered.append(name)
        return ordered


def _extract_sheet_id(url: str) -> Optional[str]:
    parts = url.split("/d/")
    if len(parts) < 2:
        return None
    remainder = parts[1]
    sheet_id = remainder.split("/")[0]
    return sheet_id or None

