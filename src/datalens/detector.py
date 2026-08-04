"""Guesses what each column really holds.

Two rules this module exists to enforce:
  1. it OPINES, it never converts - changing the data is cleaning.py's job. That
     separation is what lets the user correct a wrong guess before it becomes data;
  2. every guess carries a confidence, so the screen can say "date, 72%" instead of
     pretending to be sure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Sequence

import pandas as pd

# A guess needs a STRICT majority to win. Exactly half is a coin flip, not a guess -
# and a coin flip that converts a column destroys data.
MIN_MATCH_RATIO = 0.5

# Below this share of distinct values, a text column is a category, not free text.
MAX_CATEGORY_RATIO = 0.5

# Currency symbols and spaces (including the non-breaking space Excel loves).
_NOISE = re.compile(r"[R$€£\s ]")

# Not numbers, even though float() accepts them.
_NOT_NUMBERS = {"nan", "inf", "-inf", "infinity", "-infinity"}

_BOOLEAN_WORDS = {
    "true",
    "false",
    "yes",
    "no",
    "y",
    "n",
    "sim",
    "nao",
    "não",
    "s",
    "verdadeiro",
    "falso",
}

# Tried in order; the format that parses the most values wins. Explicit formats
# instead of pandas' guesser because "02/01/2026" is January 2nd or February 1st
# depending on who you ask - the ambiguity has to be a decision, not a surprise.
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d/%m/%y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
)


@dataclass(frozen=True)
class DetectedType:
    """One opinion about one column.

    Frozen because a guess is a fact about the data, not a mutable setting.
    """

    column: str
    type: str  # numeric|date|boolean|category|text
    confidence: float
    failed_sample: str | None = None


def parse_number(value: Any) -> float | None:
    """Reads a number the way a Brazilian spreadsheet writes it, or returns None."""
    text = _NOISE.sub("", str(value))
    if not text or text.lower() in _NOT_NUMBERS:
        return None

    # pt-BR writes 1.234,56 - the dot groups thousands, the comma marks the decimal.
    if "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def parse_date(value: Any, date_format: str) -> datetime | None:
    """Reads one date with one explicit format, or returns None."""
    try:
        return datetime.strptime(str(value).strip(), date_format)
    except (ValueError, TypeError):
        return None


def best_date_format(texts: Sequence[str]) -> tuple[str | None, float, str | None]:
    """Picks the date format that explains the most values.

    Returns (format, match ratio, first value that did not match). cleaning.py calls
    this so it converts with the same format the detector used to decide.
    """
    best: tuple[str | None, float, str | None] = (None, 0.0, None)

    for date_format in _DATE_FORMATS:
        ratio, failed = _match_ratio(
            texts, lambda text, fmt=date_format: parse_date(text, fmt) is not None
        )
        if ratio > best[1]:
            best = (date_format, ratio, failed)

    return best


def detect(df: pd.DataFrame) -> dict[str, DetectedType]:
    """Returns one DetectedType per column. The DataFrame is only read, never touched."""
    return {str(column): _detect_column(str(column), df[column]) for column in df.columns}


# --- Internals ----------------------------------------------------------------


def _match_ratio(
    texts: Iterable[str], predicate: Callable[[str], bool]
) -> tuple[float, str | None]:
    """How much of the column the predicate explains, plus the first thing it did not."""
    matches = 0
    total = 0
    failed: str | None = None

    for text in texts:
        total += 1
        if predicate(text):
            matches += 1
        elif failed is None:
            failed = text

    if total == 0:
        return 0.0, None
    return matches / total, failed


def _detect_column(name: str, series: pd.Series) -> DetectedType:
    values = series.dropna()

    # Nothing to look at means no opinion - not a confident wrong answer.
    if values.empty:
        return DetectedType(name, "text", 0.0)

    # Booleans before numbers: pandas reports a bool column as numeric too, so
    # testing numeric first would swallow every boolean column.
    if pd.api.types.is_bool_dtype(series):
        return DetectedType(name, "boolean", 1.0)
    if pd.api.types.is_numeric_dtype(series):
        # 2024 is a number until something says otherwise, and so is 0/1. Guessing
        # "date" or "boolean" here is the kind of helpfulness that corrupts data.
        return DetectedType(name, "numeric", 1.0)
    if pd.api.types.is_datetime64_any_dtype(series):
        return DetectedType(name, "date", 1.0)

    texts = [str(value).strip() for value in values]

    ratio, failed = _match_ratio(texts, lambda text: text.lower() in _BOOLEAN_WORDS)
    if ratio > MIN_MATCH_RATIO:
        return DetectedType(name, "boolean", ratio, failed)

    ratio, failed = _match_ratio(texts, lambda text: parse_number(text) is not None)
    if ratio > MIN_MATCH_RATIO:
        return DetectedType(name, "numeric", ratio, failed)

    date_format, ratio, failed = best_date_format(texts)
    if date_format is not None and ratio > MIN_MATCH_RATIO:
        return DetectedType(name, "date", ratio, failed)

    # What is left is text. Few distinct values means the column is a label, and a
    # label is worth counting; many distinct values means free text, worth reading.
    distinct_ratio = len(set(texts)) / len(texts)
    if distinct_ratio <= MAX_CATEGORY_RATIO:
        return DetectedType(name, "category", 1.0 - distinct_ratio)
    return DetectedType(name, "text", distinct_ratio)
