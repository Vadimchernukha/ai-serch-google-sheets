from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from loguru import logger
from tqdm import tqdm

from config import Settings
from google_sheet import SheetClient
from pipeline.enricher import enrich_company


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Company enrichment CLI")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of rows to process")
    parser.add_argument("--resume", action="store_true", help="Skip rows that already have summary")
    parser.add_argument("--backup", action="store_true", help="Create CSV backup before updating")
    parser.add_argument(
        "--mode",
        choices=["basic", "extended"],
        help="Processing mode: basic (summary/products) or extended (news, articles, LinkedIn)",
    )
    parser.add_argument(
        "--profile",
        choices=["software", "iso_msp"],
        help="Profile of companies: software (default) or iso_msp",
    )
    return parser.parse_args()


def resolve_mode(provided: Optional[str]) -> str:
    if provided:
        return provided

    prompt = (
        "Select mode: [1] basic (summary/insights/products) or "
        "[2] extended (adds news/articles/LinkedIn). Default is 2: "
    )
    while True:
        try:
            choice = input(prompt).strip().lower()
        except EOFError:
            return "extended"
        if not choice and not sys.stdin.isatty():
            return "extended"
        if choice in {"", "2", "extended"}:
            return "extended"
        if choice in {"1", "basic"}:
            return "basic"
        print("Please choose 1/basic or 2/extended.")


def resolve_profile(provided: Optional[str]) -> str:
    if provided:
        return provided

    prompt = "Select profile: [1] software (default) or [2] iso_msp: "
    while True:
        try:
            choice = input(prompt).strip().lower()
        except EOFError:
            return "software"
        if not choice and not sys.stdin.isatty():
            return "software"
        if choice in {"", "1", "software"}:
            return "software"
        if choice in {"2", "iso", "iso_msp"}:
            return "iso_msp"
        print("Please choose 1/software or 2/iso_msp.")


def main() -> None:
    load_dotenv()
    args = parse_args()

    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}", level="INFO")

    settings = Settings()
    profile = resolve_profile(args.profile)
    mode = resolve_mode(args.mode)
    logger.info("Selected profile: {}", profile)
    logger.info("Selected mode: {}", mode)
    worksheet_names = settings.worksheet_for_profile(profile)
    sheet = SheetClient(settings, worksheet_name=worksheet_names)

    if args.backup:
        backup_path = settings.report_path / f"{settings.run_id}-sheet-backup.csv"
        sheet.backup_to_csv(backup_path)

    all_rows = sheet.fetch_rows()
    if not all_rows:
        logger.warning("Sheet is empty, nothing to process")
        return

    rows_to_process = list(all_rows)
    if args.resume:
        rows_to_process = [row for row in all_rows if not row.get("summary")]
    if args.limit is not None and args.limit > 0:
        rows_to_process = rows_to_process[: args.limit]

    updates: Dict[int, Dict[str, Any]] = {}

    def worker(job: Tuple[int, Dict[str, Any]]) -> Tuple[int, int, Dict[str, Any], Optional[BaseException]]:
        idx, payload = job
        try:
            enriched = enrich_company(payload, settings, profile=profile, mode=mode, index=idx)
            row_key = int(payload.get("__row", idx + 1))
            return idx, row_key, enriched, None
        except Exception as exc:  # noqa: BLE001
            row_key = int(payload.get("__row", idx + 1))
            error_payload = {**payload, "error": str(exc)}
            return idx, row_key, error_payload, exc

    jobs = list(enumerate(rows_to_process))
    with ThreadPoolExecutor(max_workers=settings.worker_count) as executor:
        futures = [executor.submit(worker, job) for job in jobs]
        for future in tqdm(as_completed(futures), total=len(futures), desc="Enriching companies"):
            idx, row_key, payload, error = future.result()
            if error:
                logger.opt(exception=error).error("Failed to enrich row {}", row_key)
            updates[row_key] = payload

    if updates:
        final_rows: List[Dict[str, Any]] = []
        for original in all_rows:
            row_key = int(original.get("__row", 0))
            final_rows.append(updates.get(row_key, original))
        sheet.batch_update(final_rows)
    else:
        logger.info("No rows were updated; keeping sheet as-is")
        final_rows = all_rows

    export_dir = settings.report_path
    export_dir.mkdir(parents=True, exist_ok=True)
    export_records = [{k: v for k, v in row.items() if k != "__row"} for row in final_rows]
    payload = json.dumps(export_records, ensure_ascii=False, indent=2)
    json_path = export_dir / f"{settings.run_id}.json"
    csv_path = export_dir / f"{settings.run_id}.csv"
    json_path.write_text(payload, encoding="utf-8")

    try:
        import pandas as pd

        pd.DataFrame(export_records).to_csv(csv_path, index=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to write CSV backup: {}", exc)

    logger.success("Run completed: {} processed / {} total", len(rows_to_process), len(all_rows))


if __name__ == "__main__":
    main()

