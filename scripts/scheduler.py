"""Hourly background ingestion: download a limited universe, validate it against the
data contracts, and convert the SQLite warehouse into the Parquet files the app reads.

Run `python scripts/scheduler.py` from anywhere - every path is anchored on the
repository root, not on the current working directory.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_ingestion() -> None:
    """One full cycle: download -> validate -> convert to Parquet."""
    print(f"[{datetime.now()}] Starting data ingestion job...")
    script_path = PROJECT_ROOT / "scripts" / "download_data.py"

    # A limited universe keeps the hourly job cheap. Pass `--universo tudo` if you
    # want the full ~827 assets - and accept that every run rewrites 18 MB of Parquet.
    result = subprocess.run(
        [sys.executable, str(script_path), "--limite", "5"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"[{datetime.now()}] Ingestion failed:\n{result.stderr}")
        return

    print(f"[{datetime.now()}] Ingestion successful.")

    raw_dir = PROJECT_ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    db_path = PROJECT_ROOT / "data" / "exemplos" / "finance.db"

    # Validate against the data contracts (Pandera) before anything lands on disk:
    # a schema drift in the source must stop the pipeline, not get written down.
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from datalens.cleaning import enforce_data_contracts

    try:
        import pandas as pd

        connection = sqlite3.connect(db_path)

        quotes_df = pd.read_sql("SELECT * FROM quotes", connection)
        quotes_df = enforce_data_contracts(quotes_df)
        quotes_df.to_parquet(raw_dir / "quotes.parquet", index=False)

        assets_df = pd.read_sql("SELECT * FROM assets", connection)
        assets_df.to_parquet(raw_dir / "assets.parquet", index=False)

        indicators_df = pd.read_sql("SELECT * FROM indicators", connection)
        indicators_df = enforce_data_contracts(indicators_df)
        indicators_df.to_parquet(raw_dir / "indicators.parquet", index=False)

        connection.close()
        print(f"[{datetime.now()}] Parquet conversion and validation complete.")
    except Exception as error:  # noqa: BLE001 - the scheduler keeps running either way
        print(f"[{datetime.now()}] Error during validation/conversion: {error}")


if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_ingestion, "interval", hours=1, id="ingest_data_job")
    scheduler.start()

    print("Scheduler started. Press Ctrl+C to exit.")

    # Run once immediately instead of waiting for the first hourly tick.
    run_ingestion()

    try:
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("Scheduler stopped.")
