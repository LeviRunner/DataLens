"""Tests for the data contracts enforced before cleaning.

The whole point of a contract is that it fails LOUDLY and EARLY: a `close` column
with a hole, or a `date` column that is not a date, must stop the pipeline while the
cause is still visible - not poison the statistics three screens later. Pandera does
the checking; these tests pin down the promise.
"""

from __future__ import annotations

import pandas as pd
import pytest

from datalens.cleaning import clean, enforce_data_contracts


# --- The happy path: the contract coerces instead of refusing -------------------


def test_date_and_close_are_coerced_to_their_contracted_types():
    """A CSV arrives with strings; the contract turns `date` into a datetime and
    `close` into a float. Coercion IS the validation: what cannot be coerced fails.
    """
    # Arrange
    df = pd.DataFrame({"date": ["2026-01-02", "2026-01-03"], "close": ["40.5", "41.0"]})

    # Act
    result = enforce_data_contracts(df)

    # Assert
    assert result["date"].dtype.kind == "M"  # datetime64
    assert result["close"].dtype.kind == "f"  # float64
    assert result["close"].tolist() == [40.5, 41.0]


def test_brazilian_valor_column_is_also_a_mandatory_float():
    """The BCB spells its value `valor`, not `value` - the contract knows both."""
    # Act
    result = enforce_data_contracts(pd.DataFrame({"valor": ["1.23"]}))

    # Assert
    assert result["valor"].dtype.kind == "f"


# --- What the contract refuses ------------------------------------------------


def test_a_null_in_a_mandatory_value_column_is_refused():
    # Arrange
    df = pd.DataFrame({"close": [40.0, None]})

    # Act / Assert
    with pytest.raises(Exception):  # pandera.SchemaError / SchemaErrors
        enforce_data_contracts(df)


def test_a_date_column_that_is_not_a_date_is_refused():
    # Arrange
    df = pd.DataFrame({"date": ["not-a-date", "2026-01-02"]})

    # Act / Assert
    with pytest.raises(Exception):
        enforce_data_contracts(df)


# --- What the contract leaves alone -------------------------------------------


def test_a_dataframe_without_contract_columns_passes_through_unchanged():
    """A table of tickers and opening prices has no `date`, `close`, `value` or
    `valor` column - the contract must not invent constraints for it.
    """
    # Arrange
    df = pd.DataFrame({"ticker": ["PETR4.SA"], "open": [40.0]})

    # Act
    result = enforce_data_contracts(df)

    # Assert - same object, no copy made, nothing validated
    assert result is df


# --- The contract inside clean() ----------------------------------------------


def test_clean_surfaces_a_contract_break_as_a_value_error():
    """`clean()` swallows the pandera exception and speaks in the project's own
    words - the caller gets one sentence, not a schema dump.
    """
    # Arrange
    df = pd.DataFrame({"close": [40.0, None]})

    # Act / Assert
    with pytest.raises(ValueError, match="Data validation failed"):
        clean(df, types={})
