"""The opening page: the whole answer on one screen, before anybody scrolls.

THE SHAPE IS THE REQUIREMENT. A dashboard is read in one glance or it is not read: the
reader arrives with a question ("how are we doing?") and either the screen answers it
where their eyes already are, or they leave. Everything below is arranged around that
and nothing else:

    chips      what is being measured        (words, so the numbers need no caption)
    cards      five numbers, the headline    (one line each, no chart to decode)
    panels     three charts, one question each

WHY THREE CHARTS AND NOT SIX. Two rows of charts do not fit above the fold at 768px,
and a fourth chart would push the fifth card off the top. The cut is deliberate: this
page answers "what is going on", and the pages that answer "why" are one click away in
the menu. A home page that tries to hold everything holds nothing.

WHY EACH CHART IS THE CHART IT IS - the one real decision here, and it is `charts.py`
that owns the rule:
  * the benchmark over time is a LINE, because the question is a direction in time;
  * the premium per asset is a horizontal BAR, because the question is an order and
    the labels are words;
  * the split of the universe is a DONUT, because the question is "what share of the
    whole", and it has few enough parts to be honest.

NOT ONE NUMBER ON THIS PAGE IS COMPUTED HERE. The premiums, the accumulated benchmark
and the ordering all come from `datalens.ranking`, tested against values checked by
hand. This file arranges; it does not calculate.
"""

from __future__ import annotations

import theme
from sources import (
    ASSETS_QUERY,
    INDICATOR_COLUMNS,
    INDICATORS_QUERY,
    QUOTES_QUERY,
    WAREHOUSE_COLUMNS,
    from_database,
)

import streamlit as st

from datalens import charts, ranking
from datalens.connectors.base import ConnectorError
from datalens.i18n import text, translate, translator
from datalens.ranking import AnalysisError

# The Selic. The home page does not ask which benchmark - a page that opens with a
# question is a page that opens empty, and the terminal is where the choice lives.
DEFAULT_BENCHMARK = 11

# The one entry of the source selector. A value, not a sentence - see `render`.
WAREHOUSE_OPTION = "warehouse"

# Five, because five is what fits on one row at 1280px without the values wrapping -
# and because the reference has five. Each one is a different KIND of statement:
# a rate, a winner, a loser, a spread, a count. Five variations of "return" would be
# one number printed five times.
#
# Codes and not sentences: the row is drawn through the catalog, so it follows the
# session's language. `len(CHIPS)` is still what decides how many columns there are.
CHIPS = [
    "ui_chip_benchmark",
    "ui_chip_best",
    "ui_chip_worst",
    "ui_chip_volatility",
    "ui_chip_coverage",
]

# Charts fit inside the fold at this height; see `theme.CHART_HEIGHT`.
LEADERS_IN_CHART = 8


def render(connection: str) -> None:
    """Draws the home page over the example warehouse."""
    theme.page_title("Home")

    try:
        quotes = from_database(connection, QUOTES_QUERY)
        assets = from_database(connection, ASSETS_QUERY)
        rates = from_database(
            connection, INDICATORS_QUERY, {"code": DEFAULT_BENCHMARK}
        )
    except ConnectorError as error:
        # One sentence, in this session's language. The example database is shipped
        # with the project, so this is the "somebody moved the file" case.
        st.error(translate(error.message))
        return

    # THE OPTION IS AN IDENTIFIER AND THE SENTENCE IS DRAWN BY `format_func`. Putting
    # the translated sentence in the option list instead cost an afternoon: Streamlit
    # remembers the SELECTED VALUE across a re-run, so switching to Spanish left the
    # widget holding an English sentence that was no longer one of its options - and a
    # selectbox whose value is not in its options raises. Same rule as everywhere else
    # on these screens: values are stable, labels are translated.
    label = translator()
    st.selectbox(
        text("ui_data_source"),
        (WAREHOUSE_OPTION,),
        format_func=lambda _: label(
            "ui_example_warehouse", quotes=len(quotes), assets=len(assets)
        ),
        label_visibility="collapsed",
        help=text("ui_data_source_help"),
        key="home_source",
    )

    countries, sectors = _filters(assets)

    try:
        panel = ranking.price_panel(quotes, *WAREHOUSE_COLUMNS)
        universe = panel["ticker"].nunique()
        panel = panel[panel["ticker"].isin(_wanted(assets, countries, sectors))]
        benchmark = ranking.benchmark_series(rates, *INDICATOR_COLUMNS)
        scores = ranking.rank(panel, benchmark, top=panel["ticker"].nunique())
    except AnalysisError as error:
        # The usual way to get here is a filter that keeps nothing. The message names
        # what was missing, so "widen the period" reads as the instruction it is.
        st.error(translate(error.message))
        return

    theme.chips([text(code) for code in CHIPS])
    _cards(scores, universe)
    _panels(rates, scores, assets[assets["ticker"].isin(panel["ticker"].unique())])


# --- The filters --------------------------------------------------------------


def _filters(assets) -> tuple[list, list]:
    """Country and sector, in the sidebar, both empty by default.

    EMPTY MEANS EVERYTHING, and that is why nothing is pre-selected: a filter that
    arrives with three of five values ticked shows a partial answer while looking like
    a complete one, and nobody checks a filter they did not set.
    """
    st.sidebar.markdown(f"**{text('ui_please_filter')}**")
    countries = st.sidebar.multiselect(
        text("ui_region"),
        sorted(assets["country"].dropna().unique()),
        placeholder=text("ui_all_regions"),
        key="home_countries",
    )
    sectors = st.sidebar.multiselect(
        text("ui_sector"),
        sorted(assets["sector"].dropna().unique()),
        placeholder=text("ui_all_sectors"),
        key="home_sectors",
    )
    return countries, sectors


def _wanted(assets, countries: list, sectors: list):
    """The tickers that survive both filters - an empty filter keeps everything."""
    kept = assets
    if countries:
        kept = kept[kept["country"].isin(countries)]
    if sectors:
        kept = kept[kept["sector"].isin(sectors)]
    return kept["ticker"].unique()


# --- The row of numbers -------------------------------------------------------


def _cards(scores, universe: int) -> None:
    """Five numbers under the five chips, in the same order - the chip is the label.

    The best and the worst premium are BOTH here, side by side. A headline that only
    shows the winner is a headline about the winner, not about the portfolio: over the
    period this data covers, ten of twelve assets lost to the Selic, and a page that
    hides that is selling something.
    """
    best, worst = scores[0], scores[-1]
    calm = min(scores, key=lambda score: score.volatility)

    # NO `delta` ON THE PREMIUM CARDS, and it took two tries to get here. Streamlit
    # reads a delta STRING and draws an UP ARROW whenever it finds no minus sign, so
    # "vs Selic" under a premium of -176% came out as an arrow pointing up; and
    # `delta_color="off"` only greys the arrow, it does not remove it. A caption that
    # contradicts the number above it is worse than no caption, so the comparison
    # moved into the label, where Streamlit cannot draw anything on top of it.
    cards = st.columns(len(CHIPS))
    cards[0].metric(text("ui_card_selic"), f"{best.benchmark_return:.1%}")
    cards[1].metric(text("ui_card_vs_selic", ticker=best.ticker), f"{best.excess_return:+.1%}")
    cards[2].metric(text("ui_card_vs_selic", ticker=worst.ticker), f"{worst.excess_return:+.1%}")
    cards[3].metric(text("ui_card_calmest", ticker=calm.ticker), f"{calm.volatility:.1%}")
    cards[4].metric(text("ui_card_assets"), text("ui_count_of", count=len(scores), total=universe))


# --- The row of charts --------------------------------------------------------


def _panels(rates, scores, assets) -> None:
    """Three questions, three panels, left to right: when, who, and of what."""
    when, who, what = st.columns([1.1, 1.1, 0.9])

    with when, theme.panel():
        theme.panel_title(text("ui_panel_benchmark"))
        _plot(charts.time_series_chart(rates, *INDICATOR_COLUMNS))

    with who, theme.panel():
        theme.panel_title(text("ui_panel_premium"))
        # Best few and worst few, not the middle: with twelve thin bars nothing is
        # comparable, and the two ends are what the reader came for.
        ends = ranking.extremes(scores, LEADERS_IN_CHART)
        _plot(
            charts.ranked_bars(ranking.as_frame(ends), "ticker", "excess"),
            x_format=".0%",
        )

    with what, theme.panel():
        theme.panel_title(text("ui_panel_universe"))
        _plot(charts.share_pie(assets, "sector"), legend=True)


def _plot(figure, x_format: str | None = None, legend: bool = False) -> None:
    """Every chart on this page, at the one height that keeps the row above the fold.

    `x_format` is Plotly's tick format, and it is how the premium axis reads "947%"
    while the underlying column stays 9.47 - the percentage is applied at the glass,
    never baked into the data.
    """
    figure.update_layout(
        height=theme.CHART_HEIGHT,
        margin={"l": 8, "r": 8, "t": 4, "b": 4},
        showlegend=legend,
    )
    if x_format:
        figure.update_layout(xaxis_tickformat=x_format)
    # `width="stretch"` and not `use_container_width=True`: the old flag is deprecated
    # in this version of Streamlit and no longer stretches anything, which is why the
    # first draft of this page had three charts floating at 700px inside wider columns.
    st.plotly_chart(figure, width="stretch")
