"""Tests for the type detector.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from datalens.detector import DetectedType, detect

# The shape of the answer

def test_detect_returns_one_result_per_column():
    # Arrange
    df = pd.DataFrame({"ticker": ["AAPL"], "close": [210.0]})

    # Act
    result = detect(df)

    # Assert
    assert set(result) == {"ticker", "close"}
    assert all(isinstance(value, DetectedType) for value in result.values())

def test_the_result_is_immutable():
    # Arrange
    guess = detect(pd.DataFrame({"close": [1.0]}))["close"]

    # Act / Assert
    assert dataclasses.is_dataclass(guess)
    with pytest.raises(dataclasses.FrozenInstanceError):
        guess.type = "text"

def test_the_result_carries_the_column():
    # Arrange / Act
    guess = detect(pd.DataFrame({"close": [1.0, 2.0]}))["close"]

    # Assert
    assert guess.column == "close"
    assert 0.0 <= guess.confidence <= 1.0

def test_detect_does_not_modify_the_dataframe():
    # Arrange
    df = pd.DataFrame({"amount": ["R$ 1.234,56", "R$ 89,90"]})
    before = df.copy(deep=True)

    # Act
    detect(df)

    # Assert
    pd.testing.assert_extension_array_equal(df, before)

# Numeric

def test_acolumn_of_plain_numbers_is_numeric():
    # Act
    guess = detect(pd.DataFrame({"close": [40.0, 41.5, 210.0]}))["close"]

    # Assert
    assert guess.type == "numeric"
    assert guess.confidence == 1.0

def test_brazilian_currency_text_is_detected_as_numeric():
    # Act
    guess = detect(pd.DataFrame({"amount": ["R$ 1.234,56", "R$ 89,90", "R$ 12,00"]}))["amount"]

    # Assert
    assert guess.type == "numeric"

def test_a_mostly_numeric_column_is_numeric_with_reduced_confidence():
    # Arrange
    values = [str(number) for number in range(9) + ["n/a"]]

    # Act
    guess = detect(pd.DataFrame({"value": values}))["value"]

    # Assert
    assert guess.type == "numeric"
    assert guess.confidence < 1.0
    assert guess.failed_sample == "n/a"

# Dates

def test_iso_dates_are_detected_as_date():
    # Act
    guess = detect(pd.DataFrame({"date": ["2026-01-02", "2026-01-03"]}))["date"]

    # Assert
    assert guess.type == "date"
    assert guess.confidence == 1.0

def test_brazilian_dates_are_detected_as_date():
    # Act
    guess = detect(pd.DataFrame({"date": ["02/01/2026", "13/02/2026", "31/12/2025"]}))["date"]

    # Assert
    assert guess.type == "date"
    assert guess.confidence == 1.0

def test_a_year_column_of_integers_is_not_mistaken_for_a_date():
    # Act
    guess = detect(pd.DataFrame({"year": [2024, 2025, 2026]}))["year"]

    # Assert
    assert guess.type == "numeric"

# Booleans

@pytest.mark.parametrize(
    "values",
    [
        [True, False, True],
        ["sim", "não","sim"],
        ["S", "N", "S"],
        ["true", "false", "true"],
        ["yes", "no", "yes"],
    ],
)

def test_textual_booleans_are_detected_asboolean(values):
    # Act
    guess = detect(pd.DataFrame({"active": values}))["active"]

    # Assert
    assert guess.type == "boolean"

def test_zeros_and_ones_are_numeric_and_not_boolean():
    # Act
    guess = detect(pd.DataFrame({"flag": [0, 1, 1, 0]}))["flag"]

    # Assert
    assert guess.type == "numeric"

# Category vs text

def test_a_low_cardinality_text_column_is_a_category():
    # Arrange
    df = pd.DataFrame({"sector": ["Finance", "Retail", "Energy"] * 10})

    # Act
    guess = detect(df)["sector"]

    # Assert
    assert guess.type == "category"

def test_a_column_of_mostly_unique_free_text_is_text():
    # Arrange - every value distinct
    df = pd.DataFrame({"note": [f"free comment number {n}" for n in range(30)]})

    # Act
    guess = detect(df)["note"]

    # Assert
    assert guess.type == "text"

# Edge case

def test_an_all_null_column_reports_no_confidence():
    # Act
    guess = detect(pd.DataFrame({"empty": [None, None, None]}))["empty"]

    # Assert
    assert guess.confidence == 0.0

def test_nulls_are_ignored_when_measuring_confidence():
    # Act
    guess = detect(pd.DataFrame({"close": [40.0, None, 41.5, None]}))["close"]

    # Assert
    assert guess.type == "numeric"
    assert guess.confidence == 1.0

def test_an_empty_dataframe_returns_an_empty_result():
    assert detect(pd.DataFrame()) == {}

def test_detect_handles_a_dataframe_with_columns_but_no_rows():
    # Act
    result = detect(pd.DataFrame({"ticker": [], "close": []}))

    # Assert
    assert set(result) == {"ticker", "close"}
    assert all(guess.confidence == 0.0 for guess in result.values())
