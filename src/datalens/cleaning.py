"""Acts on what the detector guessed, and writes down everything it did.

The detector OPINES, the cleaning ACTS - that separation is the design decision this
module depends on.

Two properties matter more than any individual transformation:
  1. the input DataFrame is never mutated;
  2. every difference between before and after is explained by the log.

The log is what makes this module worth more than a call to `df.dropna()`: anyone can
drop nulls, few can say afterwards exactly what changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from .detector import DetectedType, best_date_format, parse_date, parse_number
from .i18n import Message, translate
import pandera as pa
from pandera.typing import Series

# Define rigid validation schemas as per Phase 1
# This schema ensures that any column named 'date' or 'data' is a datetime
# and any column named 'close', 'value', or 'valor' cannot be null.
class BaseDataContract(pa.DataFrameModel):
    class Config:
        coerce = True
        strict = False  # Allow other columns

def enforce_data_contracts(df: pd.DataFrame) -> pd.DataFrame:
    """Enforces strict data contracts using Pandera before cleaning.
    
    If 'date' or 'data' exists, it must be convertible to datetime.
    If 'close', 'value', or 'valor' exists, it cannot be null.
    """
    schema_dict = {}
    
    for col in df.columns:
        col_str = str(col).lower()
        if col_str in ("date", "data"):
            schema_dict[col] = pa.Column(pa.DateTime, coerce=True)
        elif col_str in ("close", "value", "valor"):
            schema_dict[col] = pa.Column(pa.Float, nullable=False, coerce=True)
            
    if schema_dict:
        schema = pa.DataFrameSchema(schema_dict, strict=False)
        return schema.validate(df)
    return df


# Below this, the detector is guessing rather than reading. Converting on a guess
# destroys data, and the user has not had a chance to correct it yet.
MIN_CONFIDENCE_TO_CONVERT = 0.6

VALID_STRATEGIES = ("median", "mean", "drop", "keep")

_TRUE_WORDS = {"true", "yes", "y", "sim", "s", "verdadeiro", "1"}
_FALSE_WORDS = {"false", "no", "n", "nao", "não", "falso", "0"}


@dataclass(frozen=True)
class CleaningAction:
    """One line of the cleaning log.

    `column` is empty for row-level actions, which belong to no single column.
    """

    column: str
    action: str  # dropped_duplicates|filled_missing|converted|dropped_rows
    count: int
    detail: str | None = None


def clean(
    df: pd.DataFrame,
    types: dict[str, DetectedType],
    options: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, list[CleaningAction]]:
    """Cleans a copy of `df` and returns it together with the log of what changed.

    `types` is the detector's output. `options` maps a column to a missing-value
    strategy, overriding the default for that column only.
    """
    options = options or {}
    _validate_options(options)

    # Phase 1: Validate data contracts before any cleaning
    try:
        df = enforce_data_contracts(df)
    except pa.errors.SchemaError as e:
        raise ValueError(f"Data validation failed: {e}")

    log: list[CleaningAction] = []
    result = df.copy(deep=True)

    # 1. Duplicates first: no point converting the same row twice.
    duplicates = int(result.duplicated().sum())
    if duplicates:
        result = result.drop_duplicates()
        log.append(
            CleaningAction("", "dropped_duplicates", duplicates, "identical rows")
        )

    # 2. Conversion: this is where the detector's guess finally changes the data.
    for column in result.columns:
        converted, count, failure_note = _convert(result[column], types.get(str(column)))
        if converted is None:
            continue
        result[column] = converted
        log.append(CleaningAction(str(column), "converted", count, failure_note))

    # 3. Missing values last, because step 2 creates new ones.
    for column in result.columns:
        strategy = options.get(str(column)) or _default_strategy(types.get(str(column)))
        missing = int(result[column].isna().sum())
        if not missing or strategy == "keep":
            continue

        if strategy == "drop":
            result = result[result[column].notna()].copy()
            log.append(
                CleaningAction(str(column), "dropped_rows", missing, "missing values")
            )
            continue

        filler = result[column].median() if strategy == "median" else result[column].mean()
        result[column] = result[column].fillna(filler)
        log.append(
            CleaningAction(
                str(column), "filled_missing", missing, f"{strategy} = {filler}"
            )
        )

    return result, log


# --- Internals ----------------------------------------------------------------


def _validate_options(options: dict[str, str]) -> None:
    """A typo in the config must not silently fall back to the default.

    Still a plain ValueError, so the text is not re-renderable per session like a
    ConnectorError is. It should become a ConfigError carrying a Message once
    config_loader.py exists - the strategy comes from the config file, so this is a
    config error wearing the wrong type.
    """
    for column, strategy in options.items():
        if strategy not in VALID_STRATEGIES:
            raise ValueError(
                translate(
                    Message(
                        "unknown_strategy",
                        {
                            "strategy": repr(strategy),
                            "column": repr(column),
                            "valid": ", ".join(VALID_STRATEGIES),
                        },
                    )
                )
            )


def _default_strategy(guess: DetectedType | None) -> str:
    """Median for numbers; everything else is kept.

    Imputing a category or a date would invent a fact the analysis then treats as
    real. A missing number is at least on a scale where the median means something.
    """
    if guess is not None and guess.type == "numeric":
        return "median"
    return "keep"


def _parse_boolean(value: Any) -> bool | None:
    text = str(value).strip().lower()
    if text in _TRUE_WORDS:
        return True
    if text in _FALSE_WORDS:
        return False
    return None


def _convert(
    series: pd.Series, guess: DetectedType | None
) -> tuple[pd.Series | None, int, str | None]:
    """Applies the detector's guess to one column.

    Returns (converted series, values converted, note about failures), or
    (None, 0, None) when there is nothing to do - the column is already the right
    dtype, the type is not convertible, or the guess is too weak to act on.
    """
    if guess is None or guess.confidence < MIN_CONFIDENCE_TO_CONVERT:
        return None, 0, None

    parser: Callable[[Any], Any]

    if guess.type == "numeric":
        if pd.api.types.is_numeric_dtype(series):
            return None, 0, None
        parser = parse_number
        dtype = "float64"
    elif guess.type == "boolean":
        if pd.api.types.is_bool_dtype(series):
            return None, 0, None
        parser = _parse_boolean
        dtype = "boolean"
    elif guess.type == "date":
        if pd.api.types.is_datetime64_any_dtype(series):
            return None, 0, None
        date_format, _, _ = best_date_format(
            [str(value).strip() for value in series.dropna()]
        )
        if date_format is None:
            return None, 0, None

        def parser(value, fmt=date_format):
            return parse_date(value, fmt)

        dtype = "datetime64[ns]"
    else:
        # category and text are already what they claim to be.
        return None, 0, None

    values: list[Any] = []
    failures: list[str] = []

    for value in series:
        if pd.isna(value):
            values.append(None)
            continue
        parsed = parser(value)
        if parsed is None:
            # Never lose a failure in silence: it becomes null, and the log says so.
            failures.append(str(value))
        values.append(parsed)

    converted = pd.Series(values, index=series.index, dtype=dtype)
    count = int(series.notna().sum()) - len(failures)

    note = None
    if failures:
        note = (
            f"{len(failures)} value(s) could not be converted to {guess.type} "
            f"and became null, e.g. {failures[0]!r}"
        )

    return converted, count, note
