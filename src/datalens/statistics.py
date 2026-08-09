"""Correlation and trend - the two numbers that are easiest to compute and easiest
to misread.

Two decisions hold this module together, and both are about what NOT to report:

  1. A numeric foreign key never enters a correlation. `sector_id = 2` is not twice
     `sector_id = 1`; the numbering came from the order somebody registered the
     sectors. It is the same mistake as correlating tickers, only disguised - and a
     `-0.87` carries an authority the word "AAPL" never had. The heuristic that
     recognises those columns lives in `profiling`, and is READ from there rather
     than copied: two copies of one rule drift, and then a column is excluded in one
     screen and included in the other.
  2. A trend always ships its `r_squared`. A slope on its own lets somebody claim a
     trend over four random points; the number that contradicts them has to travel
     with it, not be available on request.

The slope is per DAY, never per row. The series has holes on purpose - the market
does not open on weekends - and an x axis made of row positions makes the very same
prices "rise faster" whenever a holiday shortens the series.

CAREFUL - this module is named `statistics`, like the standard library one. Inside
the `datalens` package that works (absolute imports resolve to the stdlib), but a
strange import error in this file starts here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .detector import best_date_format, parse_date
from .i18n import Message, translate
from .profiling import profile

# --- Thresholds ---------------------------------------------------------------

# Two points always make a perfect line, so two points can never be evidence of a
# trend. Three is the first count where the fit can disagree with the data.
MIN_POINTS_FOR_TREND = 3

# A line is "flat" when the total change it predicts across the observed span is
# negligible next to the scale of the values themselves. Relative, not absolute:
# 0.01/day is noise on a share price and a landslide on a dividend yield.
FLAT_RELATIVE_CHANGE = 0.001

# Below this the slope is floating-point residue, not a direction.
FLAT_ABSOLUTE_SLOPE = 1e-12

RISING = "rising"
FALLING = "falling"
FLAT = "flat"

SECONDS_PER_DAY = 86_400.0

# The flags `profiling` publishes for every numeric column. Named because reading a
# raw string key out of a dict in three places is the drift this module avoids.
_IDENTIFIER_FLAG = "is_identifier"
_BINARY_FLAG = "is_binary_flag"


@dataclass(frozen=True)
class Trend:
    """A fitted straight line, with the number that says how much to trust it.

    Frozen for the same reason `ColumnProfile` is: a trend is a reading of the data
    at one moment, not a setting somebody edits afterwards.
    """

    column: str
    direction: str  # rising|falling|flat
    slope: float  # units of the column PER DAY
    r_squared: float


def correlation_matrix(
    df: pd.DataFrame, method: str = "pearson", exclude_identifiers: bool = True
) -> pd.DataFrame:
    """Correlates the columns worth correlating, and leaves the rest out.

    Non-numeric columns go first: there is no order in "AAPL". Then, unless the
    caller says otherwise, the numeric columns that are not measurements - foreign
    keys and 0/1 flags - because Pearson has a formula for them, a result for them,
    and no meaning for them.

    `exclude_identifiers=True` is the default because the correct path should be the
    one you get without asking. It is a default and not a prohibition: checking
    whether two IDs move together is a legitimate question - it reveals two fields
    saying the same thing - and `exclude_identifiers=False` still asks it.

    A constant column comes back as NaN, straight from pandas. That is deliberate:
    0.0 would be read as "proven unrelated", and undefined is not zero.
    """
    numeric = df.select_dtypes(include="number")

    if exclude_identifiers:
        numeric = numeric[_measurement_columns(df, numeric.columns)]

    return numeric.corr(method=method)


def detect_trend(df: pd.DataFrame, date_column: str, value_column: str) -> Trend:
    """Fits a straight line of `value_column` against time, in units per day.

    The date column may arrive as TEXT - it is what SQLite returns, since it has no
    DATE type. Requiring datetime here would break every use coming from the
    database, and the conversion would end up scattered across the callers.

    Nulls are dropped, never read as zero: a missing price treated as 0.0 invents a
    crash that never happened. A series left too short to mean anything is refused
    rather than answered.
    """
    days, values = _series_as_days_and_values(df, date_column, value_column)

    if len(values) < MIN_POINTS_FOR_TREND:
        raise ValueError(
            translate(
                Message(
                    "trend_series_too_short",
                    {
                        "count": len(values),
                        "column": repr(value_column),
                        "minimum": MIN_POINTS_FOR_TREND,
                    },
                )
            )
        )

    slope, r_squared = _fit_line(days, values)
    return Trend(
        column=value_column,
        direction=_direction(slope, days, values),
        slope=slope,
        r_squared=r_squared,
    )


# --- Internals ----------------------------------------------------------------


def _measurement_columns(df: pd.DataFrame, candidates: pd.Index) -> list[str]:
    """The numeric columns that are data, asking `profiling` which ones are not.

    The heuristic is not repeated here on purpose. `profile` already reads the NAME
    and the CARDINALITY - which is what keeps `bid` (ends in "id", is a price) and
    `volume` (an integer, and a measurement) inside the matrix, where a naive suffix
    rule would have eaten them silently.
    """
    profiles = profile(df)

    def is_measurement(column: str) -> bool:
        found = profiles.get(column)
        if found is None:
            return True
        stats = found.stats
        if stats.get(_BINARY_FLAG):
            return False
        return not stats.get(_IDENTIFIER_FLAG)

    return [str(column) for column in candidates if is_measurement(str(column))]


def _as_datetime(series: pd.Series) -> pd.Series:
    """The column as datetimes, reading the format the detector decided on.

    Reusing `best_date_format` is what keeps this module from reading 02/01 as
    February 1st while the rest of the project reads it as January 2nd.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    texts = [str(value).strip() for value in series]
    date_format, _, _ = best_date_format(texts)
    if date_format is None:
        return pd.Series([pd.NaT] * len(series), index=series.index, dtype="datetime64[ns]")

    parsed = [parse_date(text, date_format) for text in texts]
    return pd.Series(parsed, index=series.index, dtype="datetime64[ns]")


def _series_as_days_and_values(
    df: pd.DataFrame, date_column: str, value_column: str
) -> tuple[np.ndarray, np.ndarray]:
    """The two aligned axes of the fit: days since the first date, and the values.

    Days - not row positions. Three rows spanning 02/01 to 05/01 are three days, and
    the missing 04/01 (market closed) must not make the same prices look steeper.
    """
    dates = _as_datetime(df[date_column])
    values = pd.to_numeric(df[value_column], errors="coerce")

    frame = pd.DataFrame({"date": dates, "value": values}).dropna()
    if frame.empty:
        return np.array([]), np.array([])

    frame = frame.sort_values("date")
    elapsed = (frame["date"] - frame["date"].iloc[0]).dt.total_seconds()
    return (elapsed / SECONDS_PER_DAY).to_numpy(), frame["value"].astype(float).to_numpy()


def _fit_line(days: np.ndarray, values: np.ndarray) -> tuple[float, float]:
    """Least squares by hand, so the two returned numbers come from the same fit.

    `r_squared` is 0.0 when there is nothing to explain (every value identical, or
    every reading on the same day): the line explains no variation because there is
    no variation, and that is a weaker claim than NaN would suggest here.
    """
    day_variation = float(((days - days.mean()) ** 2).sum())
    value_variation = float(((values - values.mean()) ** 2).sum())

    if day_variation == 0.0 or value_variation == 0.0:
        return 0.0, 0.0

    covariance = float(((days - days.mean()) * (values - values.mean())).sum())
    slope = covariance / day_variation
    correlation = covariance / np.sqrt(day_variation * value_variation)

    return slope, float(correlation**2)


def _direction(slope: float, days: np.ndarray, values: np.ndarray) -> str:
    """Rising, falling, or no story at all.

    Not every series has a story, and reporting a trend in noise is the statistical
    form of lying. The comparison is relative to the scale of the values, so the same
    threshold works on a share price and on a percentage.
    """
    if abs(slope) <= FLAT_ABSOLUTE_SLOPE:
        return FLAT

    span_days = float(days.max() - days.min())
    scale = float(np.abs(values).mean())
    predicted_change = abs(slope) * span_days

    if scale > 0.0 and predicted_change <= FLAT_RELATIVE_CHANGE * scale:
        return FLAT

    return RISING if slope > 0 else FALLING
