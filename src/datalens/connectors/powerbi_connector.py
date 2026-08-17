"""Connector to prepare data for Power BI.

Power BI works best with a star schema or a denormalized flat table.
This script consolidates the raw parquet files into an optimized dataset 
that Power BI Desktop can connect to directly for analytical modeling.
"""

from __future__ import annotations

import duckdb
from pathlib import Path

def create_powerbi_dataset(raw_dir: Path, output_file: Path) -> None:
    """Consolidates quotes, assets, and indicators into a single Power BI ready parquet file."""
    
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    quotes_path = raw_dir / "quotes.parquet"
    assets_path = raw_dir / "assets.parquet"
    
    if not quotes_path.exists() or not assets_path.exists():
        print("Raw parquet files not found. Run the scheduler or download script first.")
        return

    # Use DuckDB to join the tables and write directly to an optimized Parquet file
    query = f"""
        COPY (
            SELECT 
                q.date,
                q.ticker,
                q.close AS price,
                a.name AS asset_name,
                a.sector,
                a.country
            FROM '{quotes_path.as_posix()}' q
            LEFT JOIN '{assets_path.as_posix()}' a ON q.ticker = a.ticker
        ) TO '{output_file.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD);
    """
    
    try:
        duckdb.sql(query)
        print(f"Power BI dataset successfully written to {output_file}")
    except Exception as e:
        print(f"Failed to create Power BI dataset: {e}")

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    raw_data_dir = project_root / "data" / "raw"
    pbi_output = project_root / "data" / "processed" / "dataset_pbi.parquet"
    
    create_powerbi_dataset(raw_data_dir, pbi_output)
