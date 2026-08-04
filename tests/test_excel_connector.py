"""Tests for the Excel connector.

What makes Excel different from CSV, and therefore what is worth testing: a workbook
holds many sheets, and the real header is often not on the first row.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from datalens.connectors.base import Connector, ConnectorError
from datalens.connectors.excel_connector import ExcelConnector


# --- The contract -------------------------------------------------------------


def test_excel_connector_satisfies_the_contract_without_inheriting_from_it(messy_workbook):
    # Arrange
    connector = ExcelConnector(str(messy_workbook))

    # Act / Assert
    assert isinstance(connector, Connector)
    assert Connector not in ExcelConnector.__mro__


# --- Sheet selection ----------------------------------------------------------


def test_load_reads_the_first_sheet_by_default(messy_workbook):
    # Act
    result = ExcelConnector(str(messy_workbook), header_row=3).load()

    # Assert
    assert list(result.columns) == ["date", "category", "amount"]


def test_load_selects_a_sheet_by_name(messy_workbook):
    # Act
    result = ExcelConnector(str(messy_workbook), sheet="Income").load()

    # Assert
    assert list(result.columns) == ["date", "source", "amount"]
    assert result["amount"][0] == 5000


def test_load_selects_a_sheet_by_index(messy_workbook):
    # Act
    result = ExcelConnector(str(messy_workbook), sheet=1).load()

    # Assert
    assert list(result.columns) == ["date", "source", "amount"]


# --- The header that is not on the first row ----------------------------------


def test_load_skips_the_junk_rows_above_the_real_header(messy_workbook):
    """The 'Expenses' sheet has a title, a date and a blank row before the header."""
    # Act
    result = ExcelConnector(str(messy_workbook), sheet="Expenses", header_row=3).load()

    # Assert
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["date", "category", "amount"]
    assert result.shape == (2, 3)


def test_the_wrong_header_row_silently_produces_garbage_columns(messy_workbook):
    """No exception - just a DataFrame whose column names are the report title.

    Same lesson as the CSV separator: the connector obeys, it does not guess.
    """
    # Act - default header_row=0 on a sheet whose header is on row 3
    result = ExcelConnector(str(messy_workbook), sheet="Expenses").load()

    # Assert
    assert list(result.columns) != ["date", "category", "amount"]


# --- Failures -----------------------------------------------------------------


def test_a_missing_file_is_reported_as_a_connector_error(tmp_path: Path):
    with pytest.raises(ConnectorError, match="File not found"):
        ExcelConnector(str(tmp_path / "nope.xlsx")).load()


def test_a_nonexistent_sheet_is_reported_as_a_connector_error(messy_workbook):
    # Arrange
    connector = ExcelConnector(str(messy_workbook), sheet="Balance")

    # Act / Assert
    with pytest.raises(ConnectorError, match="Balance"):
        connector.load()


def test_loading_every_sheet_at_once_is_refused(messy_workbook):
    """pandas returns a dict of DataFrames for sheet_name=None - that breaks the
    contract, which promises exactly one DataFrame. Refuse it at construction.
    """
    with pytest.raises(ConnectorError):
        ExcelConnector(str(messy_workbook), sheet=None)


def test_the_original_exception_is_preserved_as_the_cause(messy_workbook):
    # Arrange
    connector = ExcelConnector(str(messy_workbook), sheet="Balance")

    # Act / Assert
    with pytest.raises(ConnectorError) as caught:
        connector.load()
    assert caught.value.__cause__ is not None
