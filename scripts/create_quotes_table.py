'''create_quotes_table.py
"""Create the missing `quotes` table in the finance SQLite database.
If the table already exists, this script does nothing.
"""
import sys
from pathlib import Path
from sqlalchemy import create_engine, text, inspect

def ensure_quotes_table(db_path: str):
    path = Path(db_path).resolve()
    engine_url = f"sqlite:///{path}"
    engine = create_engine(engine_url)
    inspector = inspect(engine)
    if "quotes" in inspector.get_table_names():
        print("Table 'quotes' already exists. No action needed.")
        return
    # Define a simple schema matching typical usage
    create_stmt = text(
        """
        CREATE TABLE quotes (
            ticker TEXT NOT NULL,
            date   TEXT NOT NULL,
            close  REAL NOT NULL
        );
        """
    )
    with engine.begin() as conn:
        conn.execute(create_stmt)
    print("Table 'quotes' created successfully.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python create_quotes_table.py <sqlite_db_path>")
        sys.exit(1)
    ensure_quotes_table(sys.argv[1])
'''
