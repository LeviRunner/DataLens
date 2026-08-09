"""Describes a dataset column by column - the core of DataLens.

One design decision holds this module together: EVERY column produces the same
shape. `column`, `type`, `count`, `missing` and `missing_pct` exist for a date, a
category and a float alike; only `stats` changes with the type. That is what lets
the screen and the report loop over the result without an `if type == ...` growing
in three different files.

Two rules the module never breaks:
  1. the input DataFrame is only read, never modified - profiling is an opinion,
     like detection, and an opinion that edits the data is a bug;
  2. nulls are excluded from every statistic, never counted as zero. A missing
     price treated as 0.0 drags the mean down and invents a crash that never
     happened; 100% missing is a finding, not a failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .detector import DetectedType, best_date_format, detect, parse_date, parse_number

# --- Thresholds ---------------------------------------------------------------
# Named because a bare 0.95 in the middle of a heuristic is a decision nobody can
# review later.

# A flag needs a minimum of rows to mean anything: with a single row every column
# is "unique" and every column is "constant" at the same time.
MIN_ROWS_FOR_FLAGS = 2

# Nearly one distinct value per row - an identifier, not data to average.
PROBABLE_KEY_MIN_UNIQUE_RATIO = 0.95

# Nearly a single value in the whole column - noise in a report.
ALMOST_CONSTANT_MAX_UNIQUE_RATIO = 0.05

# An unnamed integer key is dense: 50 distinct values inside a span of ~50. A
# measure like `volume` is unique too, but spread over millions - which is exactly
# what keeps it out of the flag.
IDENTIFIER_MIN_DENSITY = 0.9

# How many categories the screen shows before it stops being a chart.
TOP_VALUES_LIMIT = 10

# Suffix/name that says "foreign key" in this schema - every FK ends in `_id`.
_IDENTIFIER_SUFFIX = "_id"
_IDENTIFIER_NAMES = {"id"}

# The two values a boolean stored as INTEGER is allowed to take (SQLite has no
# BOOLEAN, so the schema writes `INTEGER CHECK (x IN (0, 1))`).
_BINARY_VALUES = frozenset({0, 1})

_TRUE_WORDS = {"true", "yes", "y", "sim", "s", "verdadeiro", "1"}
_FALSE_WORDS = {"false", "no", "n", "nao", "não", "falso", "0"}


@dataclass(frozen=True)
class ColumnProfile:
    """Everything known about one column.

    Frozen because a profile is a reading of the data at one moment, not a
    settings object someone edits afterwards.
    """

    column: str
    type: str  # numeric|date|boolean|category|text
    count: int  # non-null values
    missing: int
    missing_pct: float
    stats: dict[str, Any]


def profile(
    df: pd.DataFrame, types: dict[str, DetectedType] | None = None
) -> dict[str, ColumnProfile]:
    """Profiles every column of `df` without touching it.

    `types` is optional on purpose: `profile(df)` asks the detector itself, while
    `profile(df, types)` accepts the guess the user already corrected on screen.
    The type is the same `DetectedType` the detector returns and `cleaning` consumes -
    one internal vocabulary, three entry doors.
    """
    guesses = types if types is not None else detect(df)

    return {
        str(column): _profile_column(str(column), df[column], guesses.get(str(column)))
        for column in df.columns
    }


# --- Internals ----------------------------------------------------------------


def _profile_column(
    name: str, series: pd.Series, guess: DetectedType | None
) -> ColumnProfile:
    """Builds the shared shape, then delegates the varying part to one builder."""
    total = int(len(series))
    missing = int(series.isna().sum())
    count = total - missing
    missing_pct = round(missing / total * 100, 2) if total else 0.0

    column_type = guess.type if guess is not None else "text"

    stats = _stats_for(column_type, series)
    stats.update(_shared_flags(name, series, column_type, count))

    return ColumnProfile(
        column=name,
        type=column_type,
        count=count,
        missing=missing,
        missing_pct=missing_pct,
        stats=stats,
    )


def _stats_for(column_type: str, series: pd.Series) -> dict[str, Any]:
    """The part of the profile that depends on the type - and the only one."""
    builders = {
        "numeric": _numeric_stats,
        "date": _date_stats,
        "boolean": _boolean_stats,
        "category": _frequency_stats,
        "text": _text_stats,
    }
    builder = builders.get(column_type, _text_stats)
    return builder(series)


def _clean(series: pd.Series) -> pd.Series:
    """The non-null values. Nulls never reach a statistic."""
    return series.dropna()


def _number(value: float | None) -> float | None:
    """NaN must not reach the screen as the string 'nan'.

    The standard deviation of a single value is undefined and pandas says so with
    NaN. `None` is the honest answer: the screen renders it as a dash, and no
    report ever prints "std: nan".
    """
    if value is None or pd.isna(value):
        return None
    return float(value)


def _as_numbers(series: pd.Series) -> pd.Series:
    """Numeric values only, reading pt-BR notation when the column is still text."""
    values = _clean(series)
    if pd.api.types.is_numeric_dtype(values):
        return values.astype("float64")
    parsed = values.map(parse_number)
    return parsed.dropna().astype("float64")


def _numeric_stats(series: pd.Series) -> dict[str, Any]:
    """Mean alone lies about skewed data, and financial data is always skewed -
    hence the quartiles next to it."""
    values = _as_numbers(series)
    if values.empty:
        return {}

    return {
        "mean": _number(values.mean()),
        "median": _number(values.median()),
        "std": _number(values.std()),
        "min": _number(values.min()),
        "max": _number(values.max()),
        "q1": _number(values.quantile(0.25)),
        "q3": _number(values.quantile(0.75)),
    }


def _as_dates(series: pd.Series) -> pd.Series:
    """Datetime values, parsed with the same format the detector decided on.

    SQLite has no DATE type: `quotes.date` arrives as ISO TEXT. Reusing
    `best_date_format` keeps the profile from reading 02/01 as February 1st while
    the detector read it as January 2nd.
    """
    values = _clean(series)
    if pd.api.types.is_datetime64_any_dtype(values):
        return values

    texts = [str(value).strip() for value in values]
    date_format, _, _ = best_date_format(texts)
    if date_format is None:
        return pd.Series([], dtype="datetime64[ns]")

    parsed = [parse_date(text, date_format) for text in texts]
    return pd.Series([value for value in parsed if value is not None], dtype="datetime64[ns]")


def _date_stats(series: pd.Series) -> dict[str, Any]:
    values = _as_dates(series)
    if values.empty:
        return {}

    first = values.min()
    last = values.max()
    return {
        "min": first,
        "max": last,
        "range_days": int((last - first).days),
    }


def _as_boolean(value: Any) -> bool | None:
    """Reads one boolean from the three shapes it arrives in: a real bool, the
    0/1 integer SQLite stores, or a word a human typed."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
        return None

    text = str(value).strip().lower()
    if text in _TRUE_WORDS:
        return True
    if text in _FALSE_WORDS:
        return False
    return None


def _boolean_stats(series: pd.Series) -> dict[str, Any]:
    """No mean here, and that is the point of the `types` parameter: once the user
    says a 0/1 column is a boolean, the average stops being offered."""
    values = [_as_boolean(value) for value in _clean(series)]
    return {
        "true_count": sum(1 for value in values if value is True),
        "false_count": sum(1 for value in values if value is False),
    }


def _frequency_stats(series: pd.Series) -> dict[str, Any]:
    """A label is worth counting - which value, and how often."""
    values = _clean(series)
    counts = values.value_counts()
    return {
        "unique": int(values.nunique()),
        "top_values": [
            (value, int(count)) for value, count in counts.head(TOP_VALUES_LIMIT).items()
        ],
    }


def _text_stats(series: pd.Series) -> dict[str, Any]:
    """Free text is not worth counting by value; its length is what describes it."""
    values = _clean(series)
    if values.empty:
        return {"unique": 0, "avg_length": None}

    lengths = values.map(lambda value: len(str(value)))
    return {
        "unique": int(values.nunique()),
        "avg_length": _number(lengths.mean()),
    }


# --- The flags the snowflake schema asked for ---------------------------------


def _shared_flags(
    name: str, series: pd.Series, column_type: str, count: int
) -> dict[str, Any]:
    """Flags every column carries, whatever its type.

    They are computed here, once, so `statistics.correlation_matrix` and the screen
    read the same decision instead of each reimplementing the heuristic - and
    drifting apart the first time one of them is "fixed".
    """
    values = _clean(series)
    unique = int(values.nunique())
    unique_ratio = unique / count if count else 0.0
    has_enough_rows = count >= MIN_ROWS_FOR_FLAGS

    flags: dict[str, Any] = {
        # Nearly one distinct value per row is an ID, not data. Note that neither
        # half of a composite key (quotes is keyed by ticker AND date) is unique on
        # its own, so neither gets flagged - that is correct, not a bug to fix.
        "is_probable_key": bool(
            has_enough_rows and unique_ratio >= PROBABLE_KEY_MIN_UNIQUE_RATIO
        ),
        "is_almost_constant": bool(
            has_enough_rows
            and (unique <= 1 or unique_ratio <= ALMOST_CONSTANT_MAX_UNIQUE_RATIO)
        ),
    }

    if column_type == "numeric":
        flags["is_binary_flag"] = _is_binary_flag(series)
        flags["is_identifier"] = _is_identifier(name, series, count, unique_ratio)

    return flags


def _integers(series: pd.Series) -> list[int] | None:
    """The column as whole numbers, or None if a single value is not one."""
    values = _as_numbers(series)
    if values.empty or not (values == values.round()).all():
        return None
    return [int(value) for value in values]


def _is_binary_flag(series: pd.Series) -> bool:
    """A numeric column whose only values are 0 and 1.

    SQLite has no BOOLEAN, so `is_business_day` arrives as 0/1 and the detector
    honestly says "numeric" - the mean of a flag is 0.66, a number that means
    nothing. Profiling does not convert it; converting is cleaning's job. It raises
    the flag so the screen can offer "correct to boolean".

    Both values are required. `direction` in `transaction_types` is -1, 0 or 1:
    three values, not a flag - and the lazy version of this heuristic ("small
    integers") would have marked it.
    """
    numbers = _integers(series)
    if numbers is None:
        return False
    return set(numbers) == _BINARY_VALUES


def _is_identifier(name: str, series: pd.Series, count: int, unique_ratio: float) -> bool:
    """A numeric foreign key: something that enters any arithmetic and should not.

    The heuristic reads the NAME and the CARDINALITY, never "it is an integer".
    `volume` is an integer and is data; the mean of `sector_id` is garbage.

    Two ways in:
      1. the name ends in `_id` - the schema's own convention for every FK;
      2. no name to go by, but the values are one dense run of whole numbers
         (unique, and packed inside a span barely wider than the row count) - what
         a surrogate key looks like. `volume` has three unique integers spread over
         half a million, so it stays out.

    Rule 2 also demands an INTEGER dtype, and that is not "it is an integer" sneaking
    back in - it is a necessary condition, not a sufficient one. A key is STORED as
    INTEGER; a measurement written as 1.0 is a float that happens to be whole. Without
    it, a three-row column reading 1.0, 2.0, 3.0 is unique, integral and dense, and
    gets flagged as a key on the screen and dropped from the correlation matrix.

    Erring towards excluding data hides analysis, and nobody sees what disappeared;
    that is why the second rule is deliberately narrow.
    """
    lowered = name.strip().lower()
    numbers = _integers(series)
    if numbers is None:
        return False

    if lowered.endswith(_IDENTIFIER_SUFFIX) or lowered in _IDENTIFIER_NAMES:
        return True

    if not pd.api.types.is_integer_dtype(series):
        return False

    if count < MIN_ROWS_FOR_FLAGS or unique_ratio < 1.0:
        return False

    span = max(numbers) - min(numbers) + 1
    return span > 0 and count / span >= IDENTIFIER_MIN_DENSITY
