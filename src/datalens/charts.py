"""Draws the profile - one chart per question, not one chart per column.

The module encodes a single decision, and it is an analysis decision, not a style
one: WHICH chart answers WHICH question. Continuous data asks "how is it spread?"
and gets a histogram; discrete data asks "how many of each?" and gets bars. A
histogram of categories is the classic mistake - it draws an order and a distance
between labels that do not exist.

Two rules the module never breaks:
  1. the input DataFrame is only read, never modified - the same contract detector
     and profiling hold;
  2. nulls are dropped, never plotted as zero. A missing price drawn at 0.0 invents
     a crash that never happened.

The one exception to rule 1 lives in `time_series_chart`, and it exists because of
the schema: SQLite has no DATE type, so `calendar.date`, `quotes.date` and
`payouts.ex_date` all arrive as TEXT. Pandas reads TEXT as `object`, and Plotly
turns an object axis into a CATEGORY axis. The chart still looks right - ISO sorts
alphabetically - which is exactly why the bug survives review. What breaks is the
DISTANCE: 02/01 and 03/03 end up side by side, evenly spaced, and the series starts
lying about time. Converting the date column to datetime before plotting is the only
conversion a chart module is entitled to make, because the time axis is a property
of the chart, not of the data.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .detector import best_date_format, parse_date

# --- Limits -------------------------------------------------------------------

# A bar chart with 500 bars is not a chart. Above this, only the most frequent
# values are drawn - and the title says so, because a silently truncated chart is
# a chart that lies.
MAX_CATEGORY_BARS = 20

# Past this many slices a pie stops being readable: the reader compares angles, and
# a slice under ~5 degrees cannot be compared with anything. The tail is grouped, not
# dropped - see `share_pie`.
MAX_PIE_SLICES = 6
_OTHER_SLICE = "other"
_DONUT_HOLE = 0.55

# A boolean has exactly two answers, and both are drawn even when one never occurs:
# "no false rows" is information, an absent bar is not.
_BOOLEAN_LABELS = ("true", "false")

_TRUE_WORDS = {"true", "yes", "y", "sim", "s", "verdadeiro", "1"}
_FALSE_WORDS = {"false", "no", "n", "nao", "não", "falso", "0"}

_LINE_MODE = "lines"


def distribution_chart(df: pd.DataFrame, column: str, column_type: str) -> go.Figure:
    """Draws how one column is distributed, choosing the chart from the type.

    `column_type` is the same vocabulary detector and profiling speak
    (numeric|date|boolean|category|text), so the screen can pass the type the user
    already corrected instead of a second guess made here.

    Raises KeyError when the column does not exist - an unknown column is a caller
    bug, and an empty figure would hide it.
    """
    values = _column(df, column).dropna()

    builders = {
        "numeric": _histogram,
        "boolean": _boolean_bars,
        "category": _category_bars,
    }
    builder = builders.get(column_type, _category_bars)

    figure = builder(values, column)
    return _label_axes(figure, x_title=column, y_title=_count_title(column_type))


def time_series_chart(
    df: pd.DataFrame,
    date_column: str,
    value_column: str,
    group_by: str | None = None,
) -> go.Figure:
    """Draws a value over time as a line, one line per group when `group_by` is given.

    The date column is converted to datetime first (see the module docstring) and the
    rows are then sorted chronologically: a `SELECT` without `ORDER BY` comes back in
    whatever order the database likes, and a line joins its points IN VECTOR ORDER -
    out of order it zigzags through a time that never happened.

    Raises ValueError when the date column cannot be read as dates. Converting it
    anyway would produce NaT everywhere and an empty chart, which the user reads as
    "there is no data" - and the question "which column is the date?" has an answer,
    known by the user.
    """
    _column(df, date_column)
    _column(df, value_column)
    if group_by is not None:
        _column(df, group_by)

    figure = go.Figure()
    if df.empty:
        return _label_axes(figure, x_title=date_column, y_title=value_column)

    frame = _chronological(df, date_column, value_column, group_by)

    if group_by is None:
        _add_line(figure, frame, date_column, value_column, name=value_column)
    else:
        for group, rows in frame.groupby(group_by, sort=True):
            _add_line(figure, rows, date_column, value_column, name=str(group))

    return _label_axes(figure, x_title=date_column, y_title=value_column)


def ranked_bars(
    df: pd.DataFrame,
    label_column: str,
    value_column: str,
    top: int = MAX_CATEGORY_BARS,
) -> go.Figure:
    """Draws a ranking: one horizontal bar per label, biggest at the top.

    HORIZONTAL, and that is the whole point of having this apart from
    `distribution_chart`. The labels here are words somebody reads - tickers, sectors,
    business types - and on a vertical axis they get rotated 45 degrees or truncated
    with an ellipsis. Read left to right, they cost nothing.

    SORTED, for the same kind of reason: a ranking drawn in the order the query
    returned makes the eye do the sorting, and the eye is bad at it. Plotly draws the
    first category at the BOTTOM, so the list is reversed on the way in - otherwise
    "biggest at the top" quietly becomes "biggest at the bottom".

    Negative values are kept, not dropped: in a table of premiums against a benchmark,
    the bars going the other way are half the answer.
    """
    frame = df.loc[:, [label_column, value_column]].dropna()
    frame = frame.sort_values(value_column, ascending=False, kind="stable").head(top)
    frame = frame.iloc[::-1]

    figure = go.Figure(
        go.Bar(
            x=frame[value_column].to_numpy(),
            y=frame[label_column].astype(str).to_numpy(),
            orientation="h",
            name=value_column,
        )
    )
    return _label_axes(figure, x_title=value_column, y_title=label_column)


def share_pie(df: pd.DataFrame, column: str, top: int = MAX_PIE_SLICES) -> go.Figure:
    """Draws how a countable column splits a whole, as proportions.

    A pie answers exactly one question - "what share of the total is each part?" - and
    it answers it badly past a handful of slices, because the reader compares angles
    and stops being able to at around 5 degrees. So everything below the top `top`
    values is GROUPED into one slice named "other" instead of being drawn as a fan of
    invisible wedges. The grouping is visible in the legend; dropping the tail instead
    would leave a pie whose parts do not add up to the whole it claims to divide.
    """
    counts = _column(df, column).dropna().astype(str).value_counts()

    shown = counts.head(top)
    labels = list(shown.index)
    values = [int(value) for value in shown.to_numpy()]

    remainder = int(counts.iloc[top:].sum())
    if remainder:
        labels.append(_OTHER_SLICE)
        values.append(remainder)

    # A hole makes it a donut: the centre is where the total goes, and the eye
    # compares arc lengths instead of trying to judge the area of a wedge.
    return go.Figure(go.Pie(labels=labels, values=values, hole=_DONUT_HOLE))


# --- Internals ----------------------------------------------------------------


def _column(df: pd.DataFrame, column: str) -> pd.Series:
    """The column, or a KeyError naming it."""
    if column not in df.columns:
        raise KeyError(f"column not found: {column!r}")
    return df[column]


def _label_axes(figure: go.Figure, x_title: str, y_title: str) -> go.Figure:
    """An unlabelled axis is a lying chart: the reader cannot tell what they see."""
    figure.update_layout(
        xaxis_title=x_title,
        yaxis_title=y_title,
    )
    return figure


def _count_title(column_type: str) -> str:
    return "frequency" if column_type == "numeric" else "count"


def _histogram(values: pd.Series, column: str) -> go.Figure:
    """Continuous data: the question is how it spreads, so the bins do the answering."""
    return go.Figure(go.Histogram(x=values, name=column))


def _category_bars(values: pd.Series, column: str) -> go.Figure:
    """Discrete data: one bar per label, capped so the chart stays readable."""
    counts = values.value_counts()
    capped = counts.head(MAX_CATEGORY_BARS)

    figure = go.Figure(go.Bar(x=list(capped.index), y=list(capped.values), name=column))
    if len(counts) > MAX_CATEGORY_BARS:
        figure.update_layout(
            title=f"{column} - top {MAX_CATEGORY_BARS} of {len(counts)} values"
        )
    return figure


def _as_boolean(value: object) -> bool | None:
    """Reads one boolean from the three shapes it arrives in: a real bool, the 0/1
    integer SQLite stores (it has no BOOLEAN type), or a word a human typed."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
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


def _boolean_bars(values: pd.Series, column: str) -> go.Figure:
    """Two bars, always. A flag has no distribution to draw - it has two counts.

    A histogram of two values sketches a spread where there is none, which is why
    the 0/1 flags of the schema (`is_business_day`, `is_tradable`) come here once the
    user corrects the detector's honest "numeric".
    """
    read = [_as_boolean(value) for value in values]
    counts = {
        "true": sum(1 for value in read if value is True),
        "false": sum(1 for value in read if value is False),
    }
    return go.Figure(
        go.Bar(
            x=list(_BOOLEAN_LABELS),
            y=[counts[label] for label in _BOOLEAN_LABELS],
            name=column,
        )
    )


def _as_datetime(values: pd.Series, column: str) -> pd.Series:
    """The column as real datetimes, read with the format the detector decided on.

    Reusing `best_date_format` is what keeps the chart from reading 02/01 as
    February 1st while the detector read it as January 2nd - one dataset, one
    reading of the dates.
    """
    if pd.api.types.is_datetime64_any_dtype(values):
        return values

    texts = [str(value).strip() for value in values.dropna()]
    date_format, _, failed = best_date_format(texts)
    if date_format is None:
        raise ValueError(
            f"column {column!r} does not hold dates; first value read: {failed!r}"
        )

    parsed = values.map(
        lambda value: None if pd.isna(value) else parse_date(value, date_format)
    )
    converted = pd.to_datetime(parsed, errors="coerce")
    if converted.notna().sum() == 0:
        raise ValueError(f"column {column!r} does not hold dates")
    return converted


def _chronological(
    df: pd.DataFrame,
    date_column: str,
    value_column: str,
    group_by: str | None,
) -> pd.DataFrame:
    """The rows a line may be drawn from: real dates, no nulls, in time order."""
    columns = [date_column, value_column]
    if group_by is not None:
        columns.append(group_by)

    frame = df.loc[:, columns].copy()
    frame[date_column] = _as_datetime(frame[date_column], date_column)

    frame = frame.dropna(subset=columns)
    return frame.sort_values(date_column, kind="stable")


def _add_line(
    figure: go.Figure,
    frame: pd.DataFrame,
    date_column: str,
    value_column: str,
    name: str,
) -> None:
    """One line. `name` is not decoration: without it the legend says "trace 0" and
    nobody can tell which line is Petrobras."""
    figure.add_trace(
        go.Scatter(
            x=frame[date_column].to_numpy(),
            y=frame[value_column].to_numpy(),
            mode=_LINE_MODE,
            name=name,
        )
    )
