from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import gspread
import pandas as pd
from loguru import logger

from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound

from config import Settings


class SheetClient:
    def __init__(
        self, settings: Settings, worksheet_name: Optional[Sequence[str] | str] = None
    ) -> None:
        self._settings = settings
        self._client = gspread.service_account_from_dict(settings.service_account_info())

        try:
            spreadsheet = self._client.open_by_key(settings.gsheet_id)
        except SpreadsheetNotFound as exc:
            raise RuntimeError(
                "Google Sheet not found or access denied. Share the document with the service account email."
            ) from exc

        if worksheet_name is None:
            candidates: List[str] = [settings.gsheet_worksheet]
        elif isinstance(worksheet_name, str):
            candidates = [worksheet_name]
        else:
            candidates = list(worksheet_name)

        if settings.gsheet_worksheet and settings.gsheet_worksheet not in candidates:
            candidates.append(settings.gsheet_worksheet)
        if "Sheet1" not in candidates:
            candidates.append("Sheet1")

        worksheet = None
        last_exception: Optional[WorksheetNotFound] = None
        for name in candidates:
            if not name:
                continue
            try:
                worksheet = spreadsheet.worksheet(name)
                logger.debug("Using worksheet '%s'", name)
                break
            except WorksheetNotFound as exc:
                last_exception = exc
                continue

        if worksheet is None:
            raise RuntimeError(
                "Worksheet not found. Tried: " + ", ".join(filter(None, candidates))
            ) from last_exception

        self._worksheet = worksheet
        self._header: Optional[List[str]] = None

    def fetch_rows(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        raw_values = self._worksheet.get_all_values()
        if not raw_values:
            return []

        header = raw_values[0]
        self._header = header

        records: List[Dict[str, Any]] = []
        for excel_row, row_values in enumerate(raw_values[1:], start=2):
            record: Dict[str, Any] = {header[idx]: row_values[idx] if idx < len(row_values) else "" for idx in range(len(header))}
            record["__row"] = excel_row
            records.append(record)

        max_items = self._settings.max_companies if self._settings.max_companies > 0 else None
        if limit and limit > 0:
            max_items = min(limit, max_items) if max_items else limit

        if max_items:
            records = records[:max_items]

        logger.info("Fetched {} rows from Google Sheet", len(records))
        return records

    def batch_update(self, records: List[Dict[str, Any]]) -> None:
        if not records:
            logger.warning("No records provided for update")
            return

        df = pd.DataFrame(records)
        if "__row" in df.columns:
            df = df.drop(columns=["__row"])

        column_order: List[str] = []
        if self._header:
            column_order.extend(self._header)
        column_order = [
            col
            for col in column_order
            if col not in {"has_products", "product_names", "geography"}
        ]
        for col in df.columns.tolist():
            if col not in column_order:
                column_order.append(col)
        if column_order:
            df = df.reindex(columns=column_order)

        df = df.fillna("")

        values = [df.columns.tolist()] + df.astype(str).values.tolist()
        logger.info("Updating sheet with {} rows and {} columns", df.shape[0], df.shape[1])
        self._worksheet.clear()
        self._worksheet.update(values)

    def backup_to_csv(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        all_values = self._worksheet.get_all_records()
        pd.DataFrame(all_values).to_csv(destination, index=False)
        logger.info("Backup saved to {}", destination)
        return destination

