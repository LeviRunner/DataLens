"""Crossing share prices with a macroeconomic benchmark, and ordering the result.

This is the only module in the project that produces a RECOMMENDATION. Everything
else describes what happened; a Top 10 says "this one". Four decisions follow from
that difference, and each one is a thing the module refuses to do:

  1. IT RANKS BY RISK-ADJUSTED EXCESS, NOT BY RETURN. The question the dashboard asks
     is not "which one went up the most" - a savings account answers that badly and a
     lottery ticket answers it beautifully. It is "which one paid the most for the
     risk it took, on top of what the money would have earned sitting in the CDI".
     That number has a name (the Sharpe ratio against the risk-free rate) and one
     definition, so nobody has to trust a weighting somebody invented.

  2. THERE IS NO WEIGHTED SUM. The tempting design is `0.4*return + 0.3*volatility +
     0.2*rsi + 0.1*trend`. Those four weights are four opinions with no source, and
     the total they produce - "87 points" - carries an authority no part of it earned.
     The moving average and the RSI are computed and REPORTED, never mixed into the
     score: they say something about today's timing, and the score is about the whole
     period. Two questions, two numbers, side by side.

  3. THE BENCHMARK IS COMPOUNDED, NEVER SUMMED. The Selic arrives as a percentage per
     DAY (`0.052`). Over 252 business days, adding gives 13.10% and compounding gives
     13.98%. Both look plausible on screen and only one is the money.

  4. PRICE AND BENCHMARK ARE PAIRED BY DATE. A holiday in Brazil that is a trading day
     in New York shifts one series against the other, and from that row on every
     American share is being measured against the interest of a different day. The
     pairing is `join(how="inner")` on the date, so a ticker is only ever judged over
     the days both series actually have.

WHAT THIS MODULE DOES NOT KNOW: where the data came from. It takes a tidy panel and a
rate series, both already loaded by the connectors - so the same ranking runs over the
example CSV, over the warehouse and over a live call to the Banco Central, and the app
above it stays a drawer of widgets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from .detector import best_date_format, parse_number
from .i18n import DataLensError, Message

# --- The constants that carry a decision --------------------------------------

# Business days in a year, the market convention. Volatility is annualised with the
# SQUARE ROOT of it: variance grows with time, and the standard deviation with its
# root. Multiplying by 252 instead of by ~15.87 inflates risk sixteenfold - and does
# it to every asset equally, so the ranking still looks sane while the number is
# nonsense.
TRADING_DAYS_PER_YEAR = 252

# Below this there is no ranking, there is a coin toss. Two months of history is also
# what the 50-day average and the 14-day RSI need before they mean anything. A newly
# listed share is EXCLUDED rather than ranked: with five points its volatility is
# noise, and a small denominator is how a three-day IPO reaches first place.
MIN_TRADING_DAYS = 60

TOP_BY_DEFAULT = 10

RSI_WINDOW = 14
TREND_WINDOW = 50

# Wilder's thresholds, quoted as such. They are conventions, not laws, and the module
# reports them as an observation about today - never as a reason to rank.
OVERBOUGHT = 70.0
OVERSOLD = 30.0

# An annualised volatility under 25% reads as calm for a single share; a fall of more
# than 30% from a peak is the kind of ride the table has to warn about.
CALM_VOLATILITY = 0.25
DEEP_DRAWDOWN = -0.30

# The smallest volatility the Sharpe ratio is allowed to divide by, as an annualised
# figure (0.01%). A perfectly constant return has zero risk by measurement, not by
# nature, and dividing by it yields `inf` - which sorts to the top and recommends the
# asset the data knows the least about. The floor keeps the number finite and still
# ranks a steady asset above a jumpy one with the same return.
MIN_VOLATILITY = 1e-4

PERCENT = 100.0

# How many values the detector needs to settle on ONE date format. Reading the
# format off a million rows costs a second and changes nothing: the candidate
# formats already disagree within the first few hundred values.
_DATE_SAMPLE = 500

_PANEL_COLUMNS = ("ticker", "date", "price")


class AnalysisError(DataLensError):
    """The data cannot support a ranking, and the message says which part.

    Same contract as `ConnectorError`: a code and its parameters, never a sentence.
    "Invalid data" is not a message - the caller needs to know whether to fix a column
    name, a date format, or the length of the history.
    """


@dataclass(frozen=True)
class Score:
    """One asset measured against the benchmark, with the reasons attached.

    Frozen like `ColumnProfile` and `Trend`: a score is a reading of a period that
    already happened, not a setting anybody edits afterwards.

    `reasons` are `Message` objects - codes and parameters - and not sentences, for
    exactly the reason `i18n` exists: the screen that shows them has a language
    selector, and a sentence built here would be built in one language.
    """

    ticker: str
    days: int
    total_return: float
    benchmark_return: float
    excess_return: float
    volatility: float
    sharpe: float
    max_drawdown: float
    rsi: float
    above_trend: bool
    reasons: tuple[Message, ...]


# --- Reading the two inputs ---------------------------------------------------


def price_panel(
    frame: pd.DataFrame,
    ticker_column: str = "ticker",
    date_column: str = "date",
    price_column: str = "close",
) -> pd.DataFrame:
    """Normalises any quote table into the panel the ranking reads: ticker/date/price.

    The conversion lives here and not in the connectors on purpose - a connector
    hands over what the source sent, and five connectors each converting `1.234,56`
    in their own way is five chances to be wrong. The number parser and the date
    format both come from `detector`, so a price is read the same way here, in the
    cleaning and in the profile.

    Raises:
        AnalysisError: when a column is missing, when no date could be read, or when
            nothing survives the conversion.
    """
    _require_columns(frame, (ticker_column, date_column, price_column))

    # VAZIO É VAZIO, e não "ilegível". Sem esta linha, um frame sem nenhuma linha cai
    # em `_as_dates`, que não acha formato de data em zero valores e acusa
    # "não consegui ler a coluna como datas" - mandando o leitor investigar o formato
    # de um dado que não existe. Foi exatamente o que apareceu na tela quando o app
    # abriu no meio de um download: as cotações já estavam gravadas, a tabela de
    # indicadores ainda não.
    if frame.empty:
        raise AnalysisError("ranking_no_prices", column=price_column)

    panel = pd.DataFrame(
        {
            "ticker": frame[ticker_column].astype(str),
            "date": _as_dates(frame[date_column], date_column),
            "price": _as_numbers(frame[price_column]),
        }
    ).dropna()

    if panel.empty:
        raise AnalysisError("ranking_no_prices", column=price_column)

    # `keep="last"` on a repeated (ticker, date): a re-sent day corrects the earlier
    # one, it does not add a second day to the series.
    return (
        panel.sort_values(["ticker", "date"])
        .drop_duplicates(["ticker", "date"], keep="last")
        .reset_index(drop=True)
    )


def benchmark_series(
    frame: pd.DataFrame,
    date_column: str = "date",
    rate_column: str = "value",
    per_cent: bool = True,
) -> pd.Series:
    """Normalises a macro series into a daily rate indexed by date.

    `per_cent=True` is the shape the Banco Central sends (SGS 11 is "% a.d.", so
    `0.052` means 0.052% in a day, i.e. 0.00052). Leave it on unless the source
    already speaks in decimals - getting it wrong multiplies the CDI by a hundred,
    and the excess of every share turns deeply negative at once.

    Raises:
        AnalysisError: when the columns are missing, the dates unreadable, or nothing
            is left after the conversion.
    """
    _require_columns(frame, (date_column, rate_column))

    # Mesmo motivo do painel de preços: uma série que voltou sem linha nenhuma diz
    # isso, e não que as datas dela são ilegíveis.
    if frame.empty:
        raise AnalysisError("ranking_no_benchmark", column=rate_column)

    rates = _as_numbers(frame[rate_column])
    series = pd.Series(
        rates.to_numpy(), index=_as_dates(frame[date_column], date_column)
    ).dropna()

    if per_cent:
        series = series / PERCENT

    # A repeated date is one day of interest, not two. Same rule as the panel.
    series = series[~series.index.duplicated(keep="last")].sort_index()

    if series.empty:
        raise AnalysisError("ranking_no_benchmark", column=rate_column)

    return series.rename("rate")


# --- The ranking --------------------------------------------------------------


def rank(
    panel: pd.DataFrame,
    benchmark: pd.Series,
    top: int = TOP_BY_DEFAULT,
    minimum_days: int = MIN_TRADING_DAYS,
) -> list[Score]:
    """Scores every ticker against the benchmark and returns the best `top` of them.

    Ordered by `sharpe` - excess over the benchmark per unit of risk taken. Ordering
    by `excess_return` alone would put the most leveraged, most volatile name first
    every time, which is a ranking of appetite, not of quality.

    Args:
        panel: the output of `price_panel` - ticker, date, price.
        benchmark: the output of `benchmark_series` - a daily rate by date.
        top: how many rows the table wants.
        minimum_days: history below which a ticker is left out rather than ranked.

    Raises:
        AnalysisError: when no ticker has enough paired history. An empty table with
            no explanation reads as "no share is any good"; the error names the
            number of days that were missing.
    """
    scores = [
        _score_one(str(ticker), rows, benchmark)
        for ticker, rows in panel.groupby("ticker", sort=True)
        if _paired(rows, benchmark).shape[0] >= minimum_days
    ]

    if not scores:
        raise AnalysisError("ranking_history_too_short", minimum=minimum_days)

    return sorted(scores, key=lambda score: score.sharpe, reverse=True)[:top]


def extremes(scores: list[Score], count: int) -> list[Score]:
    """The best and the worst few, in ranking order, with nobody counted twice.

    The obvious `scores[:n] + scores[-n:]` is wrong as soon as the list is shorter than
    `2n`: with six assets and four a side, the two in the middle appear in both halves
    and get drawn TWICE - as two bars stacked on the same row, which reads as one wider
    bar and quietly overstates them. It only shows up once a filter narrows the
    universe, which is to say in front of a user and not in a test.
    """
    if len(scores) <= count:
        return list(scores)

    half = count // 2
    return list(scores[:half]) + list(scores[len(scores) - (count - half) :])


def as_frame(scores: list[Score]) -> pd.DataFrame:
    """The scores as a table, in the order they were ranked.

    Exists so that a SCREEN never has to build a DataFrame out of dataclasses just to
    hand it to a chart - that little loop is data shaping, and data shaping in the
    file that draws buttons is how business rules start living in the UI.

    Every number stays a DECIMAL fraction (0.39, not 39). Percentages are a display
    format, and the formatting belongs where the display is; a column that is already
    multiplied by a hundred silently breaks the next thing that tries to compute with
    it. `reasons` is left out: it holds `Message` objects, which are not a table cell.
    """
    return pd.DataFrame(
        [
            {
                "ticker": score.ticker,
                "days": score.days,
                "return": score.total_return,
                "benchmark": score.benchmark_return,
                "excess": score.excess_return,
                "volatility": score.volatility,
                "sharpe": score.sharpe,
                "drawdown": score.max_drawdown,
                "rsi": score.rsi,
                "above_trend": score.above_trend,
            }
            for score in scores
        ]
    )


def _paired(rows: pd.DataFrame, benchmark: pd.Series) -> pd.DataFrame:
    """Price and rate on the days BOTH series have - the inner join of decision 4."""
    prices = pd.Series(rows["price"].to_numpy(), index=pd.DatetimeIndex(rows["date"]))
    return pd.DataFrame({"price": prices}).join(benchmark, how="inner").sort_index()


def _score_one(ticker: str, rows: pd.DataFrame, benchmark: pd.Series) -> Score:
    """Every number for one ticker, over the days it shares with the benchmark."""
    paired = _paired(rows, benchmark)

    # The first paired day has no eve, so it produces no return. The benchmark is
    # accumulated over the SAME days as the returns, or the two sides of the excess
    # would cover different periods.
    returns = paired["price"].pct_change().dropna()
    rates = paired["rate"].reindex(returns.index)

    total_return = float((1 + returns).prod() - 1)
    benchmark_return = float((1 + rates).prod() - 1)

    excess_daily = returns - rates
    volatility = float(excess_daily.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))

    # GEOMETRIC, not the mean of the daily excesses. The arithmetic mean ignores that
    # a fall of 50% needs a rise of 100% to undo, so it flatters exactly the assets
    # that swing the most - and the table then shows a share with a -37% premium
    # sitting above one with -11%, both "risk-adjusted". Whatever orders the rows has
    # to be the same quantity the rows display.
    annual_excess = _annualised(total_return, len(returns)) - _annualised(
        benchmark_return, len(returns)
    )
    sharpe = annual_excess / max(volatility, MIN_VOLATILITY)

    excess_return = total_return - benchmark_return
    max_drawdown = float((paired["price"] / paired["price"].cummax() - 1).min())
    rsi = _relative_strength_index(paired["price"])
    above_trend = _above_trend(paired["price"])

    return Score(
        ticker=ticker,
        days=len(paired),
        total_return=total_return,
        benchmark_return=benchmark_return,
        excess_return=excess_return,
        volatility=volatility,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        rsi=rsi,
        above_trend=above_trend,
        reasons=_reasons(excess_return, volatility, max_drawdown, rsi, above_trend),
    )


def _annualised(total: float, days: int) -> float:
    """A return accumulated over `days` trading days, restated per year.

    Compounded, so that two windows of different lengths can be compared at all: a
    period shorter than a year would otherwise look worse than it was, and a longer
    one better.
    """
    if days <= 0 or total <= -1:
        return 0.0
    return (1 + total) ** (TRADING_DAYS_PER_YEAR / days) - 1


# --- The two timing indicators (reported, never scored) -----------------------


def _relative_strength_index(prices: pd.Series, window: int = RSI_WINDOW) -> float:
    """Wilder's RSI at the last day, 0 to 100.

    The smoothing is exponential with `alpha = 1/window`, which is Wilder's own
    average and not the simple mean of the last 14 days - the two disagree by enough
    to move a value across the 70 line, and the thresholds quoted everywhere are his.
    """
    change = prices.diff().dropna()
    if len(change) < window:
        return float("nan")

    smoothing = {"alpha": 1 / window, "adjust": False, "min_periods": window}
    average_gain = change.clip(lower=0).ewm(**smoothing).mean().iloc[-1]
    average_loss = (-change.clip(upper=0)).ewm(**smoothing).mean().iloc[-1]

    # No losing day in the window: the ratio is infinite and the index saturates at
    # 100. Letting the division happen would put `inf` on the screen.
    if average_loss == 0:
        return 100.0

    return float(100 - 100 / (1 + average_gain / average_loss))


def _above_trend(prices: pd.Series, window: int = TREND_WINDOW) -> bool:
    """Whether the last close sits above its own moving average."""
    if len(prices) < window:
        return False
    return bool(prices.iloc[-1] > prices.iloc[-window:].mean())


# --- Saying why ---------------------------------------------------------------


def _reasons(
    excess_return: float,
    volatility: float,
    max_drawdown: float,
    rsi: float,
    above_trend: bool,
) -> tuple[Message, ...]:
    """The sentences behind a position, as codes - one per thing that was measured.

    A ranking that shows only its order asks to be trusted. Every number that made the
    order is named here, INCLUDING the ones against the asset: a leader with a 40% fall
    from its peak has to say so on the same line where it is being praised.
    """
    reasons = [
        Message(
            "reason_beat_benchmark" if excess_return >= 0 else "reason_lost_to_benchmark",
            {"excess": _as_percent(abs(excess_return))},
        ),
        Message(
            "reason_calm" if volatility < CALM_VOLATILITY else "reason_volatile",
            {"volatility": _as_percent(volatility)},
        ),
        Message(
            "reason_deep_drawdown"
            if max_drawdown <= DEEP_DRAWDOWN
            else "reason_shallow_drawdown",
            {"drawdown": _as_percent(abs(max_drawdown))},
        ),
        Message(
            "reason_above_trend" if above_trend else "reason_below_trend",
            {"window": TREND_WINDOW},
        ),
    ]

    if rsi == rsi:  # not NaN
        if rsi >= OVERBOUGHT:
            reasons.append(Message("reason_overbought", {"rsi": f"{rsi:.0f}"}))
        elif rsi <= OVERSOLD:
            reasons.append(Message("reason_oversold", {"rsi": f"{rsi:.0f}"}))

    return tuple(reasons)


# --- Shared checks ------------------------------------------------------------


def _require_columns(frame: pd.DataFrame, required: tuple[str, ...]) -> None:
    """Fails naming the missing column AND the ones that are there.

    "Missing column" is useless when the file calls the price `fechamento`: what the
    reader needs is the list to choose the right name from.
    """
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise AnalysisError(
            "ranking_missing_column",
            column=", ".join(missing),
            available=", ".join(str(name) for name in frame.columns),
        )


def _as_numbers(column: pd.Series) -> pd.Series:
    """The column as floats, without paying the Brazilian parser when it is not needed.

    `parse_number` handles `R$ 1.234,56` one value at a time, in Python. That is the
    right tool for a CSV exported from Excel and the wrong one for a million rows the
    database already handed over as REAL: converting a float to text and back again,
    a million times, is the difference between a page that opens and a page that
    hangs. Measured on the full warehouse - 827 assets, ~1M quotes - this is the
    single change that took `price_panel` from tens of seconds to under one.

    A column that is ALREADY numeric passes straight through. Only text goes through
    the parser, which is exactly where the comma-decimal rule matters.
    """
    if pd.api.types.is_numeric_dtype(column):
        return column
    return column.map(parse_number)


def _as_dates(column: pd.Series, name: str) -> pd.Series:
    """Reads a date column with ONE format, chosen by the detector for the whole column.

    Per-value guessing is what turns `02/01/2026` into 2 January on one row and 1
    February on the next, inside the same file. The format is decided once, from the
    whole column, by the same function `cleaning` uses - and then applied to the whole
    column at once by pandas, instead of a million `strptime` calls in Python.

    The format is sampled, not read from every row: `best_date_format` only needs
    enough values to tell the candidate formats apart, and a million-row column costs
    a second just to turn into a list of strings.
    """
    if pd.api.types.is_datetime64_any_dtype(column):
        return column

    present = column.dropna()
    sample = present.iloc[:_DATE_SAMPLE] if len(present) > _DATE_SAMPLE else present
    date_format, ratio, _ = best_date_format([str(value) for value in sample])

    if date_format is None or ratio == 0:
        raise AnalysisError("ranking_unreadable_dates", column=name)

    # `errors="coerce"` and not a raise: a single malformed row becomes NaT and is
    # dropped by the caller, which is what `parse_date` returning None already did.
    return pd.to_datetime(column, format=date_format, errors="coerce")


def _as_percent(value: float) -> str:
    """One decimal place and a sign - the message templates take text, not floats."""
    return f"{value * 100:.1f}%"
