""" Tests for the cleaning pipeline.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from datalens.cleaning import CleaningAction, clean
from datalens.detector import detect

# The two properties that matter

def test_clean_does_does_not_mutate_the_input_dataframe():
    # Arrange
    df = pd.DataFrame({"value": [1.0, None, 1.0]})
    before = df.copy(deep=True)

    # Act
    clean(df, detect(df))

    # Assert
    pd.testing.assert_frame_equal(df, before)

def test_every_action_in_the_log_is_immutable():
    # Arrange
    df = pd.DataFrame({"value": [1.0, 1.0]})

    # Act
    clean(df, detect(df))

    # Assert
    pd.testing.assert_frame_equal(df, before)

def test_a_dataframe_that_needs_nothing_produces_an_empty_log():
    # Arrange
    df = pd.DataFrame({"ticker": ["AAPL", "PETR4.SA"], "close": [210.0, 40.0]})

    # Act
    result, log = clean(df, detect(df))

    # Assert
    assert log == []
    pd.testing.assert_frame_equal(result, df)

# Duplicates

def test_duplicate_rows_are_removed_and_couted():
    # Arrange
    df = pd.DataFrame({"ticker": ["AAPL", "AAPL", "PETR4.SA"], "close": [210.0, 210.0, 40.0]})

    # Act
    result, log = clean(df, detect(df))

    # Assert
    assert len(result) == 2
    assert any(action.action == "dropped_duplicates" and action.count == 1 for action in log)

# Missing values

def test_missing_numeric_values_are_filled_with_the_median_by_default():
    # Arrange - median of [10, 20, 30] is 20
    df = pd.DataFrame({"value": [10.0, 20.0, 30.0, None]})

    # Act
    result, log = clean(df, detect(df))

    # Assert
    assert result["value"].isna().sum() == 0
    assert result["value"].iloc[3] == 20.0
    assert any(action.action == "filled_missing" and action.count == 1 for action in log)

def test_the_missing_strategy_can_be_chosen_per_column():
    # Arrange
    df = pd.DataFrame({"value": [10.0, 20.0, None]})

    # Act
    result, log = clean(df, detect(df), options={"value": "drop"})

    # Assert
    assert len(result) == 2
    assert any(action.action == "dropped_rows" for action in log)

def test_keeping_missing_values_is_a_valid_choice():
    # Arrange
    df = pd.DataFrame({"value": [10.0, None]})

    # Act
    result, _ = clean(df, detect(df), options={"value": "keep"})

    # Assert
    assert result["value"].isna().sum() == 1

def test_an_unknown_strategy_fails_loudly():
    # Arrange
    df = pd.DataFrame({"value": [1.0, None]})

    # Act / Assert
    with pytest.raises(ValueError, match="mediana"):
        clean(df, detect(df), options={"value": "mediana"})

# Type conversion

def test_a_brazilian_currency_column_becomes_numeric():
    # Arrange
    df = pd.DataFrame({"amount": ["R$ 1.234,56", "R$ 89,90"]})

    # Act
    result, log = clean(df, detect(df))

    # Assert
    assert pd.api.types.is_numeric_dtype(result["amount"])
    assert result["amount"].iloc[0] == 1234.56
    assert any(action.action == "converted" for action in log)

def test_values_that_fail_conversion_become_null_and_are_logged_with_an_example():
    # Arrange
    df = pd.DataFrame({"value": ["10", "20", "n/a"]})

    # Act
    result, log = clean(df, detect(df), options={"value": "keep"})

    # Assert
    assert result["values"].isna().sum() == 1
    failures = [action for action in log if action.action == "converted"]
    assert failures and "n/a" in (failures[0].detail or "")

def test_a_low_confidence_guess_is_not_applied():
    # Arrange
    df + pd.DataFrame({"mixed": ["10", "banana", "20", "orange"]})

    # Act
    result, _ = clean(df, detect(df))

    # Assert
    assert not pd.api.types.is_numeric_dtype(result["mixed"])

# The log explains everything

def test_the_log_accounts_for_the_change_in_row_count():
    # Arrange
    df = pd.DataFrame({"value": [1.0, 1.0, 2.0]})

    # Act
    result, log = clean(df, detect(df), options={"value": "drop"})

    # Assert
    removed = sum(
        action.count for action in log if action.action in {"dropped_duplicates", "dropped_rows"} 
    )
    assert len(df) - len(result) == removed

def test_every_logged_action_names_a_real_column():
    # Arrange
    df = pd.DataFrame({"value": [1.0, None], "other": ["a", "b"]})

    # act
    _, log = clean(df, detect(df))

    # Assert
    assert all(action.column in df.column for action in log if action.column)
