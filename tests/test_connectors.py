"""Tests for the connectors: the shared contract and the SQL connector.

What is worth testing here:
  - the contract holds (a connector satisfies it WITHOUT inheriting from it);
  - every failure surfaces as ConnectorError, never as a raw stack trace;
  - bind parameters really neutralise SQL injection.

What is not worth testing: that SQLAlchemy and pandas work. They have their own tests.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine

from datalens.connectors.base import Connector, ConnectorError, validate_path
from datalens.connectors.sql_connector import SQLConnector


# --- The contract -------------------------------------------------------------


def test_sql_connector_satisfies_the_contract_without_inheriting_from_it(sample_db):
    # Arrange
    connector = SQLConnector(sample_db, "SELECT 1")

    # Act / Assert - this is the whole point of Protocol over an abstract base class
    assert isinstance(connector, Connector)
    assert Connector not in SQLConnector.__mro__


def test_an_object_without_load_does_not_satisfy_the_contract():
    class NotAConnector:
        def read(self) -> None: ...

    assert not isinstance(NotAConnector(), Connector)


# --- validate_path ------------------------------------------------------------


def test_validate_path_returns_a_path_for_an_existing_file(tmp_path: Path):
    # Arrange
    target = tmp_path / "data.csv"
    target.write_text("ticker,close\nAAPL,210.0\n", encoding="utf-8")

    # Act
    result = validate_path(target)

    # Assert
    assert result == target
    assert isinstance(result, Path)


@pytest.mark.parametrize(
    "case, expected_message",
    [
        ("empty", "Empty file path"),
        ("missing", "File not found"),
        ("directory", "directory"),
    ],
)
def test_validate_path_rejects_unusable_paths(tmp_path: Path, case, expected_message):
    # Arrange
    path = {"empty": "   ", "missing": tmp_path / "nope.csv", "directory": tmp_path}[case]

    # Act / Assert
    with pytest.raises(ConnectorError, match=expected_message):
        validate_path(path)


# --- SQLConnector: the happy path ---------------------------------------------


def test_load_returns_the_query_result_as_a_dataframe(sample_db):
    # Arrange
    connector = SQLConnector(sample_db, "SELECT ticker, date, close FROM quotes")

    # Act
    result = connector.load()

    # Assert
    assert isinstance(result, pd.DataFrame)
    assert result.shape == (3, 3)
    assert list(result.columns) == ["ticker", "date", "close"]


def test_load_binds_named_parameters_instead_of_interpolating_them(sample_db):
    # Arrange
    connector = SQLConnector(
        sample_db,
        "SELECT close FROM quotes WHERE ticker = :ticker ORDER BY date",
        {"ticker": "PETR4.SA"},
    )

    # Act
    result = connector.load()

    # Assert
    assert list(result["close"]) == [40.0, 41.5]


# --- SQLConnector: the security property --------------------------------------


def test_a_malicious_parameter_is_treated_as_data_and_not_executed(sample_db):
    """The reason bind parameters exist: the value never becomes SQL."""
    # Arrange
    attack = "'; DROP TABLE quotes; --"
    connector = SQLConnector(
        sample_db, "SELECT COUNT(*) AS n FROM quotes WHERE ticker = :ticker", {"ticker": attack}
    )

    # Act
    result = connector.load()

    # Assert - it matched nothing, and the table is still standing
    assert result["n"][0] == 0
    survivors = SQLConnector(sample_db, "SELECT COUNT(*) AS n FROM quotes").load()
    assert survivors["n"][0] == 3


# --- SQLConnector: every failure is a ConnectorError ---------------------------


@pytest.mark.parametrize(
    "connection, query",
    [
        ("", "SELECT 1"),
        ("   ", "SELECT 1"),
        ("sqlite:///x.db", ""),
        ("sqlite:///x.db", "   "),
    ],
)
def test_empty_connection_or_query_is_rejected_at_construction(connection, query):
    """Fail fast: no point opening a database to run nothing."""
    with pytest.raises(ConnectorError):
        SQLConnector(connection, query)


def test_an_invalid_dialect_is_reported_as_a_connection_string_problem():
    # Arrange
    connector = SQLConnector("banana://host/db", "SELECT 1")

    # Act / Assert
    with pytest.raises(ConnectorError, match="Invalid connection string"):
        connector.load()


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM",  # syntax error
        "SELECT * FROM cotacoes",  # table does not exist
        "SELECT fechamento FROM quotes",  # column does not exist
    ],
)
def test_a_broken_query_is_reported_as_a_connector_error(sample_db, query):
    """pandas wraps the SQLAlchemy error in pandas.errors.DatabaseError, which does
    NOT inherit from SQLAlchemyError. Catching only SQLAlchemyError would let these
    escape as a raw stack trace - this test is what keeps that regression out.
    """
    # Arrange
    connector = SQLConnector(sample_db, query)

    # Act / Assert
    with pytest.raises(ConnectorError, match="Failed to execute query"):
        connector.load()


def test_the_original_exception_is_preserved_as_the_cause(sample_db):
    """`raise ... from error` keeps the real cause in the traceback."""
    # Arrange
    connector = SQLConnector(sample_db, "SELECT * FROM nonexistent_table")

    # Act / Assert
    with pytest.raises(ConnectorError) as caught:
        connector.load()
    assert caught.value.__cause__ is not None


# --- SQLConnector: referential integrity is alive, not just declared ------------


def test_an_orphan_row_is_refused_by_the_snowflake(snowflake_db):
    """`PRAGMA foreign_keys = ON` is per CONNECTION in SQLite, not per database. The
    schema declares the foreign keys either way; only the pragma makes them bite.
    'GHOST' is not in `assets`, so this INSERT has to be refused.
    """
    # Arrange
    connector = SQLConnector(
        snowflake_db,
        "INSERT INTO quotes (ticker, date, close) VALUES ('GHOST', '2026-01-02', 1.0)",
    )

    # Act / Assert
    with pytest.raises(ConnectorError) as caught:
        connector.load()
    assert caught.value.message.code == "sql_foreign_key_violation"


def test_foreign_keys_false_lets_the_same_orphan_row_in(snowflake_db):
    """The contrast is what proves the listener does the work: same database, same
    statement, only the flag changed. `foreign_keys=False` stays legitimate for bulk
    loading, where rows arrive out of dependency order.
    """
    # Arrange
    writer = SQLConnector(
        snowflake_db,
        "INSERT INTO quotes (ticker, date, close) VALUES ('GHOST', '2026-01-02', 1.0)",
        foreign_keys=False,
    )

    # Act
    writer.load()

    # Assert - the orphan really landed, it was not just tolerated in memory
    survivors = SQLConnector(
        snowflake_db, "SELECT COUNT(*) AS n FROM quotes WHERE ticker = 'GHOST'"
    ).load()
    assert survivors["n"][0] == 1


def test_the_pragma_holds_on_the_second_connection_of_the_same_engine(snowflake_db):
    """The exact pool bug the event listener exists for.

    SQLAlchemy pools connections: running the pragma once right after `connect()`
    protects ONE connection, and the next query may be served by another. The two
    connections are opened at the same time on purpose - that forces the pool to hand
    out a second, brand-new DBAPI connection instead of recycling the first.
    """
    # Arrange
    connector = SQLConnector(snowflake_db, "SELECT 1")
    engine = create_engine(snowflake_db)
    connector._enforce_foreign_keys(engine)

    # Act
    try:
        with engine.connect() as first, engine.connect() as second:
            pragmas = [
                first.exec_driver_sql("PRAGMA foreign_keys").scalar(),
                second.exec_driver_sql("PRAGMA foreign_keys").scalar(),
            ]
    finally:
        engine.dispose()

    # Assert
    assert pragmas == [1, 1]


# --- SQLConnector: reading the snowflake ---------------------------------------


def test_a_join_across_the_snowflake_returns_the_flattened_rows(snowflake_db):
    """A fact table only becomes readable joined to its dimension: `quotes` knows the
    ticker, `assets` knows the name. This is what the connector is ultimately for.
    """
    # Arrange
    connector = SQLConnector(
        snowflake_db,
        "SELECT q.ticker, a.name AS asset_name, q.close "
        "FROM quotes q JOIN assets a ON a.ticker = q.ticker "
        "WHERE q.ticker = :ticker ORDER BY q.date",
        {"ticker": "PETR4.SA"},
    )

    # Act
    result = connector.load()

    # Assert
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["ticker", "asset_name", "close"]
    assert list(result["close"]) == [40.0, 41.5]
    assert set(result["asset_name"]) == {"Petrobras PN"}


# --- SQLConnector: the connection string is a credential -----------------------


def test_the_password_of_a_connection_string_never_reaches_the_error():
    """A connection string carries a secret. Handing `repr(self.connection)` to the
    message parameters leaks that password into the structured log AND onto the
    screen - two places where a database password must never be written down.
    """
    # Arrange
    connector = SQLConnector("postgresql://user:senha@host/db", "SELECT 1")

    # Act
    with pytest.raises(ConnectorError) as caught:
        connector.load()
    error = caught.value

    # Assert - not in the English sentence, not in the parameters that build any other
    assert "senha" not in str(error)
    assert all("senha" not in str(value) for value in error.message.params.values())
    assert "***" in str(error)
    assert "host/db" in str(error)  # still identifies WHICH database failed
