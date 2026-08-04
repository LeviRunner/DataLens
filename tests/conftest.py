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


@pytest.fixture
def clean_csv(tmp_path: Path) -> Path:
    """A well-behaved CSV: comma separated, UTF-8, dot decimal."""
    path = tmp_path / "quotes.csv"
    path.write_text(
        "ticker,date,close\n"
        "PETR4.SA,2026-01-02,40.0\n"
        "PETR4.SA,2026-01-03,41.5\n"
        "AAPL,2026-01-02,210.0\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def brazilian_csv(tmp_path: Path) -> Path:
    """The classic CSV exported by Excel in pt-BR.

    Semicolon separator, comma decimal, latin-1 encoding, accented header. Reading
    it with the defaults produces garbage rather than an exception - which is why
    the connector takes these three as parameters instead of guessing.
    """
    path = tmp_path / "brazilian.csv"
    path.write_bytes(
        "ticker;data;preço\n"
        "PETR4.SA;02/01/2026;40,50\n"
        "VALE3.SA;02/01/2026;61,20\n".encode("latin-1")
    )
    return path


@pytest.fixture
def messy_workbook(tmp_path: Path) -> Path:
    """A workbook with the two classics that break scripts.

    Sheet "Expenses": three junk rows before the real header (header_row=3).
    Sheet "Income":   header on the first row (header_row=0).
    """
    from openpyxl import Workbook

    path = tmp_path / "personal_finance.xlsx"
    book = Workbook()

    expenses = book.active
    expenses.title = "Expenses"
    expenses.append(["Personal finance report"])
    expenses.append(["Generated on 02/01/2026"])
    expenses.append([])
    expenses.append(["date", "category", "amount"])
    expenses.append(["02/01/2026", "food", "R$ 1.234,56"])
    expenses.append(["03/01/2026", "transport", "R$ 89,90"])

    income = book.create_sheet("Income")
    income.append(["date", "source", "amount"])
    income.append(["05/01/2026", "salary", 5000])

    book.save(path)
    return path
