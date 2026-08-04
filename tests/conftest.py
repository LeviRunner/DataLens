"""Shared test setup.

The project uses a `src/` layout without being pip-installed, so `src` has to be
on `sys.path` before the tests can import `datalens`.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture
def sample_db(tmp_path: Path) -> str:
    """A tiny throwaway SQLite database, returned as a SQLAlchemy URL.

    Tests own their data: they never touch data/exemplos/finance.db, so a broken
    test can't corrupt the real database and a changed database can't break a test.
    """
    path = tmp_path / "test.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE quotes (
            ticker TEXT,
            date   TEXT,
            close  REAL NOT NULL,
            PRIMARY KEY (ticker, date)
        );
        INSERT INTO quotes VALUES
            ('PETR4.SA', '2026-01-02', 40.0),
            ('PETR4.SA', '2026-01-03', 41.5),
            ('AAPL',     '2026-01-02', 210.0);
        """
    )
    connection.commit()
    connection.close()
    return f"sqlite:///{path}"
