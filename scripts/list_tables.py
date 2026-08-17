'''list_tables.py
"""Utility to list tables in a SQLite database using SQLAlchemy.
Usage:
    python list_tables.py <database_path>
Example:
    python list_tables.py "C:/study/Old DataLens/DataLens/data/exemplos/finance.db"
"""
import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect

def list_tables(db_path: str):
    # Ensure path is absolute and formatted for SQLAlchemy URI
    path = Path(db_path).resolve()
    engine_url = f"sqlite:///{path}"
    engine = create_engine(engine_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if not tables:
        print("The database is completely empty. No tables exist.")
    else:
        print(f"Found these tables: {tables}")
        # Optionally, list columns for each table
        for tbl in tables:
            cols = [col["name"] for col in inspector.get_columns(tbl)]
            print(f"- {tbl}: columns = {cols}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python list_tables.py <sqlite_database_path>")
        sys.exit(1)
    list_tables(sys.argv[1])
'''
