"""Tests for the CSV connector.

The interesting cases are not "does pandas read a CSV" - it does. They are:
  - does the connector honour separator/encoding/decimal instead of guessing;
  - does every failure arrive as a ConnectorError with an actionable message.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from datalens.connectors.base import Connector, ConnectorError
from datalens.connectors.csv_connector import CSVConnector


# --- The contract -------------------------------------------------------------


def test_csv_connector_satisfies_the_contract_without_inheriting_from_it(clean_csv):
    # Arrange
    connector = CSVConnector(str(clean_csv))

    # Act / Assert
    assert isinstance(connector, Connector)
    assert Connector not in CSVConnector.__mro__


# --- The happy path -----------------------------------------------------------


def test_load_reads_a_well_behaved_csv_with_the_defaults(clean_csv):
    # Arrange
    connector = CSVConnector(str(clean_csv))

    # Act
    result = connector.load()

    # Assert
    assert isinstance(result, pd.DataFrame)
    assert result.shape == (3, 3)
    assert list(result.columns) == ["ticker", "date", "close"]
    assert result["close"][0] == 40.0


def test_load_accepts_a_path_object_and_not_only_a_string(clean_csv: Path):
    """validate_path takes `str | Path`, so the connector should too."""
    # Act
    result = CSVConnector(clean_csv).load()

    # Assert
    assert result.shape == (3, 3)


# --- The reason the parameters exist ------------------------------------------


def test_load_reads_a_brazilian_csv_when_told_the_right_parameters(brazilian_csv):
    # Arrange
    connector = CSVConnector(
        str(brazilian_csv), separator=";", encoding="latin-1", decimal=","
    )

    # Act
    result = connector.load()

    # Assert - "40,50" became the number 40.5, not the string "40,50"
    assert list(result.columns) == ["ticker", "data", "preço"]
    assert result["preço"][0] == 40.5
    assert pd.api.types.is_numeric_dtype(result["preço"])


def test_the_wrong_separator_silently_produces_a_single_column(brazilian_csv):
    """The dangerous case: no exception, just wrong data.

    This is why detection is the detector's job (day 10) and not the connector's -
    and why the user needs to be able to correct the guess.
    """
    # Arrange - right encoding, but the default comma separator
    connector = CSVConnector(str(brazilian_csv), encoding="latin-1")

    # Act
    result = connector.load()

    # Assert - everything collapsed into one column instead of three
    assert result.shape[1] == 1


# --- Failures -----------------------------------------------------------------


def test_a_missing_file_is_reported_as_a_connector_error(tmp_path: Path):
    # Arrange
    connector = CSVConnector(str(tmp_path / "does_not_exist.csv"))

    # Act / Assert
    with pytest.raises(ConnectorError, match="File not found"):
        connector.load()


def test_a_directory_is_reported_as_a_connector_error(tmp_path: Path):
    with pytest.raises(ConnectorError, match="directory"):
        CSVConnector(str(tmp_path)).load()


def test_an_empty_file_is_reported_as_a_connector_error(tmp_path: Path):
    # Arrange
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")

    # Act / Assert
    with pytest.raises(ConnectorError, match="empty"):
        CSVConnector(str(path)).load()


def test_the_wrong_encoding_suggests_the_fix(brazilian_csv):
    """A latin-1 file read as utf-8 raises - and the message should say what to try."""
    # Arrange
    connector = CSVConnector(str(brazilian_csv), separator=";", encoding="utf-8")

    # Act / Assert
    with pytest.raises(ConnectorError, match="latin-1"):
        connector.load()


def test_ragged_rows_are_reported_as_a_connector_error(tmp_path: Path):
    # Arrange - row 2 has more fields than the header
    path = tmp_path / "ragged.csv"
    path.write_text("a,b\n1,2\n3,4,5,6,7\n", encoding="utf-8")

    # Act / Assert
    with pytest.raises(ConnectorError):
        CSVConnector(str(path)).load()


def test_the_original_exception_is_preserved_as_the_cause(brazilian_csv):
    # Arrange
    connector = CSVConnector(str(brazilian_csv), separator=";", encoding="utf-8")

    # Act / Assert
    with pytest.raises(ConnectorError) as caught:
        connector.load()
    assert isinstance(caught.value.__cause__, UnicodeDecodeError)
