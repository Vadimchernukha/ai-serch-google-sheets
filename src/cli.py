from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from dotenv import load_dotenv
from loguru import logger
from tqdm import tqdm

from config import Settings
from google_sheet import SheetClient
from pipeline.enricher import collect_dossier, collect_media, collect_profile

app = typer.Typer(help="Top Scraper CLI")

load_dotenv()


def _resolve_sheet(settings: Settings, profile: str) -> SheetClient:
    worksheet = settings.worksheet_for_profile(profile)
    return SheetClient(settings, worksheet_name=worksheet)


def _backup_sheet(sheet: SheetClient, settings: Settings) -> Path:
    path = settings.report_path / f"{settings.run_id}-sheet-backup.csv"
    sheet.backup_to_csv(path)
    return path


def _merge_rows(all_rows: List[Dict[str, Any]], updates: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    final_rows: List[Dict[str, Any]] = []
    for original in all_rows:
        row_key = int(original.get("__row", 0))
        final_rows.append(updates.get(row_key, original))
    return final_rows


def _select_rows(
    rows: List[Dict[str, Any]],
    *,
    resume_field: Optional[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    selected = rows
    if resume_field:
        selected = [row for row in rows if not row.get(resume_field)]
    if limit is not None and limit > 0:
        selected = selected[:limit]
    return selected


@app.command()
def scrape(
    profile: str = typer.Option("software", help="Target profile: software or iso_msp"),
    limit: Optional[int] = typer.Option(None, help="Max number of rows to process"),
    resume: bool = typer.Option(False, help="Skip rows that already have a summary"),
    backup: bool = typer.Option(False, help="Backup the sheet before updating"),
) -> None:
    """Stage 1: core enrichment (summary, insights, software signals)."""

    settings = Settings()
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {message}", level="INFO")

    sheet = _resolve_sheet(settings, profile)
    if backup:
        path = _backup_sheet(sheet, settings)
        logger.info("Sheet backup saved to {}", path)

    all_rows = sheet.fetch_rows()
    if not all_rows:
        logger.warning("Sheet is empty. Nothing to process")
        return

    target_rows = _select_rows(all_rows, resume_field="baseline_summary" if resume else None, limit=limit)
    if not target_rows:
        logger.info("No rows selected for Stage 1")
        return

    logger.info("Processing {} rows (profile: {})", len(target_rows), profile)

    updates: Dict[int, Dict[str, Any]] = {}
    jobs = list(enumerate(target_rows))

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=settings.worker_count) as executor:
        future_map = {
            executor.submit(collect_profile, row, settings, profile, idx): (idx, row)
            for idx, row in jobs
        }
        for future in tqdm(as_completed(future_map), total=len(future_map), desc="Stage 1"):
            idx, original_row = future_map[future]
            row_key = int(original_row.get("__row", idx + 1))
            try:
                enriched = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.opt(exception=exc).error("Stage 1 failed for row {}", row_key)
                continue
            updates[row_key] = enriched

    if not updates:
        logger.warning("No rows were updated during Stage 1")
        return

    final_rows = _merge_rows(all_rows, updates)
    sheet.batch_update(final_rows)
    _export_snapshot(settings, final_rows)
    logger.success("Stage 1 completed: {} rows updated", len(updates))


@app.command()
def media(
    profile: str = typer.Option("software", help="Target profile: software or iso_msp"),
    limit: Optional[int] = typer.Option(None, help="Max number of rows to process"),
    resume: bool = typer.Option(False, help="Skip rows that already have latest_news"),
) -> None:
    """Stage 2: add news, articles, LinkedIn signals."""

    settings = Settings()
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {message}", level="INFO")

    sheet = _resolve_sheet(settings, profile)
    all_rows = sheet.fetch_rows()
    if not all_rows:
        logger.warning("Sheet is empty. Nothing to process")
        return

    resume_field = "news_highlight" if resume else None
    target_rows = _select_rows(all_rows, resume_field=resume_field, limit=limit)
    if not target_rows:
        logger.info("No rows selected for Stage 2")
        return

    updates: Dict[int, Dict[str, Any]] = {}
    for idx, row in enumerate(tqdm(target_rows, desc="Stage 2")):
        row_key = int(row.get("__row", idx + 1))
        try:
            enriched = collect_media(row, settings, profile, idx)
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=exc).error("Stage 2 failed for row {}", row_key)
            continue
        updates[row_key] = enriched

    if not updates:
        logger.warning("No rows were updated during Stage 2")
        return

    final_rows = _merge_rows(all_rows, updates)
    sheet.batch_update(final_rows)
    _export_snapshot(settings, final_rows)
    logger.success("Stage 2 completed: {} rows updated", len(updates))


@app.command()
def dossier(
    profile: str = typer.Option("software", help="Target profile to read rows from"),
    limit: Optional[int] = typer.Option(None, help="Max number of rows to process"),
    resume: bool = typer.Option(
        False,
        help="Skip rows that already have a dossier_summary (use --resume to enable)",
    ),
) -> None:
    """Stage 3: deep dive dossier via Perplexity research."""

    settings = Settings()
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {message}", level="INFO")

    if not settings.perplexity_api_key:
        raise typer.BadParameter("PERPLEXITY_API_KEY is required for Stage 3")

    sheet = _resolve_sheet(settings, profile)
    all_rows = sheet.fetch_rows()
    if not all_rows:
        logger.warning("Sheet is empty. Nothing to process")
        return

    resume_field = "dossier_summary" if resume else None
    target_rows = _select_rows(all_rows, resume_field=resume_field, limit=limit)
    if not target_rows:
        logger.info("No rows selected for Stage 3")
        return

    updates: Dict[int, Dict[str, Any]] = {}
    for idx, row in enumerate(tqdm(target_rows, desc="Stage 3")):
        row_key = int(row.get("__row", idx + 1))
        try:
            enriched = collect_dossier(row, settings, idx)
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=exc).error("Stage 3 failed for row {}", row_key)
            continue
        updates[row_key] = enriched

    if not updates:
        logger.warning("No rows were updated during Stage 3")
        return

    final_rows = _merge_rows(all_rows, updates)
    sheet.batch_update(final_rows)
    _export_snapshot(settings, final_rows)
    logger.success("Stage 3 completed: {} rows updated", len(updates))


def _export_snapshot(settings: Settings, rows: List[Dict[str, Any]]) -> None:
    export_dir = settings.report_path
    export_dir.mkdir(parents=True, exist_ok=True)

    payload = [{k: v for k, v in row.items() if k != "__row"} for row in rows]
    json_path = export_dir / f"{settings.run_id}.json"
    csv_path = export_dir / f"{settings.run_id}.csv"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        import pandas as pd

        pd.DataFrame(payload).to_csv(csv_path, index=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to write CSV snapshot: {}", exc)


if __name__ == "__main__":
    app()
