'''open_duckdb.py
"""Start a local DuckDB instance and expose the `quotes` view.

Usage:
    python open_duckdb.py          # opens an interactive DuckDB shell
    python open_duckdb.py --run    # runs a test query and exits

The script:
1. Connects to (or creates) the DuckDB file at
   C:/study/DataLens/data/duckdb/finance.duckdb
2. Installs and loads the Parquet extension.
3. Creates a view `quotes` that reads from
   C:/study/DataLens/data/raw/quotes.parquet (if the file exists).
4. If called with ``--run`` it prints the first 5 rows of the view and exits.
   Otherwise it drops you into an interactive DuckDB REPL.
"""
import argparse
import pathlib
import sys
import subprocess

import duckdb

# ---------------------------------------------------------------------------
# Configuration – adjust paths if your project layout changes
# ---------------------------------------------------------------------------
BASE = pathlib.Path(r"C:/study/DataLens")
DB_PATH = BASE / "data" / "duckdb" / "finance.duckdb"
PARQUET_PATH = BASE / "data" / "raw" / "quotes.parquet"

def ensure_db_and_view():
    """Create the DuckDB file (if missing) and the ``quotes`` view.
    The view is created as a *VIEW* – it reads the Parquet file lazily each time.
    If the Parquet file does not exist we simply skip the view creation.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    # Enable Parquet support (built‑in but needs to be loaded)
    con.execute("INSTALL parquet; LOAD parquet;")
    if PARQUET_PATH.exists():
        con.execute(f"""
            CREATE OR REPLACE VIEW quotes AS
            SELECT * FROM read_parquet('{PARQUET_PATH}');
        """)
        print(f"[✓] View `quotes` ready (reading from {PARQUET_PATH})")
    else:
        print(f"[⚠] Parquet file not found at {PARQUET_PATH}. View not created.")
    con.close()

def run_interactive():
    """Launch the DuckDB REPL attached to our database file."""
    # ``duckdb`` binary may be available in the environment; fall back to Python REPL.
    try:
        subprocess.run(["duckdb", str(DB_PATH)], check=True)
    except FileNotFoundError:
        # If the CLI binary is not in PATH, use the Python console as a fallback.
        print("DuckDB CLI not found – falling back to Python REPL.")
        con = duckdb.connect(str(DB_PATH))
        try:
            import code
            code.interact(local={"con": con})
        finally:
            con.close()

def run_test_query():
    """Execute a quick SELECT to verify the view works and exit."""
    con = duckdb.connect(str(DB_PATH))
    try:
        # Load Parquet extension (safe even if already loaded)
        con.execute("INSTALL parquet; LOAD parquet;")
        if "quotes" in con.execute("SHOW TABLES").fetchall():
            rows = con.execute("SELECT * FROM quotes LIMIT 5").fetchdf()
            print(rows)
        else:
            print("The `quotes` view does not exist. Ensure the parquet file is present.")
    finally:
        con.close()

def main():
    parser = argparse.ArgumentParser(description="Start local DuckDB with DataLens config")
    parser.add_argument("--run", action="store_true", help="Run a test query and exit")
    args = parser.parse_args()

    ensure_db_and_view()
    if args.run:
        run_test_query()
    else:
        run_interactive()

if __name__ == "__main__":
    main()
'''
