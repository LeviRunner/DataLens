"""The investment terminal: prices on one side, the macro rate on the other, ranked.

Same rule as `streamlit_app.py` - this file reads input, calls `src/datalens/` and
draws the answer. Not one number on this screen is computed here: the compounding of
the Selic, the annualisation of the volatility, the pairing by date and the ordering
all live in `datalens.ranking`, where they are tested with values checked by hand.

THREE THINGS THIS FILE OWNS, AND THEY ARE ALL ABOUT THE USER, NOT ABOUT THE DATA:

  * THE CACHE. A benchmark series is a slow HTTP call to the Banco Central, and a
    Streamlit script re-runs top to bottom on every widget the user touches. Without
    `@st.cache_data`, moving a date slider would call the BCB again - and a few of
    those in a row is how an IP gets a 429. The cache is keyed by the arguments, so a
    new period is a new call and the same period never is.
    `st.cache_data` hands each caller a COPY of the cached value, which is what makes
    the editable workspace below safe: editing the table cannot reach into the cache.
    (`st.cache_resource` shares one object and would not be safe here.)

  * THE LEGENDS. Every field says what it does, and every source says what it brings.
    A form that asks for "SGS code" and gives nothing back teaches the user to leave
    the default alone forever.

  * THE HONESTY OF THE TABLE. The ranking is ordered by risk-adjusted excess over the
    benchmark and the screen says so, next to the reasons - including the ones against
    the asset. A Top 10 that shows only its order is asking to be believed.
"""

from __future__ import annotations

from datetime import date, timedelta

import sources
import streamlit as st
from sources import (
    ASSETS_QUERY,
    BCB_COLUMNS,
    BCB_SERIES,
    BCB_URL,
    INDICATOR_COLUMNS,
    INDICATORS_QUERY,
    QUOTES_QUERY,
    WAREHOUSE_COLUMNS,
)
from uploads import to_temporary_path

from datalens import ranking
from datalens.connectors.base import ConnectorError
from datalens.i18n import text, translate, translator
from datalens.ranking import AnalysisError

DEFAULT_YEARS = 3

# The two ways to feed the ranking, named once so the radio and the branch that reads
# it cannot drift apart. They are catalog CODES, not sentences: the radio prints them
# through `text()`, so the option follows the session's language while
# `prices_from == LOADED` keeps comparing one stable string.
WAREHOUSE = "ui_prices_warehouse"
LOADED = "ui_prices_loaded"


# --- The form -----------------------------------------------------------------


def _sources_form(connection: str, loaded_columns: list[str]) -> dict | None:
    """Every parameter of the run, in one form, each field saying what it is for.

    One form and one button, not eight widgets that each trigger a re-run: a screen
    that reloads while somebody is still typing the second date is a screen that calls
    the BCB with a half-filled period.
    """
    with st.expander(text("ui_sources_form"), expanded=True):
        # OUTSIDE the form on purpose. Nothing inside a `st.form` re-renders until it
        # is submitted, so with the radio in there the three column selectors were on
        # screen even when the warehouse was chosen - three questions about a table
        # nobody had picked. Out here the radio triggers a cheap re-run (it downloads
        # nothing; only the button does) and the mapping appears when it is relevant.
        prices_from = st.radio(
            text("ui_prices"),
            (WAREHOUSE, LOADED),
            format_func=translator(),
            horizontal=True,
            help=text("ui_prices_help"),
            key="term_prices_from",
        )
        mapping = (
            _column_mapping(loaded_columns)
            if prices_from == LOADED
            else WAREHOUSE_COLUMNS
        )
        if prices_from == LOADED and not loaded_columns:
            st.warning(text("ui_nothing_loaded"))

        with st.form("terminal_sources"):
            left, right = st.columns(2)
            with left:
                start = st.date_input(
                    text("ui_from"),
                    value=date.today() - timedelta(days=365 * DEFAULT_YEARS),
                    help=text("ui_from_help"),
                    key="term_start",
                )
            with right:
                end = st.date_input(text("ui_to"), value=date.today(), key="term_end")

            # The SGS labels stay as they are: "Selic (SGS 11)" is the name of a series
            # at the Banco Central, not a sentence to translate.
            benchmark_code = st.selectbox(
                text("ui_benchmark"),
                [code for code, series in BCB_SERIES.items() if series["daily_rate"]],
                format_func=lambda code: BCB_SERIES[code]["label"],
                help=text("ui_benchmark_help"),
                key="term_benchmark",
            )
            live = st.checkbox(
                text("ui_live_download"),
                value=False,
                help=text("ui_live_download_help"),
                key="term_live",
            )
            context_codes = st.multiselect(
                text("ui_context_series"),
                [code for code in BCB_SERIES if not BCB_SERIES[code]["daily_rate"]],
                format_func=lambda code: BCB_SERIES[code]["label"],
                help=text("ui_context_series_help"),
                key="term_context",
            )
            top = st.slider(
                text("ui_how_many"), 3, 20, ranking.TOP_BY_DEFAULT, key="term_top"
            )

            st.info(text("ui_how_the_cross_works", url=BCB_URL.format(code=11)))

            if not st.form_submit_button(text("ui_submit")):
                return None

    return {
        "start": start,
        "end": end,
        "benchmark_code": benchmark_code,
        "live": live,
        "context_codes": context_codes,
        "top": top,
        "connection": connection,
        "prices_from": prices_from,
        "columns": mapping,
    }


def _column_mapping(columns: list[str]) -> tuple[str, str, str]:
    """Which of the loaded table's columns hold ticker, date and price.

    Asked rather than guessed. A file that calls the close `fechamento` is not a
    broken file, and a screen that silently picks the wrong column produces a ranking
    that is confidently about the volume.
    """
    if not columns:
        return WAREHOUSE_COLUMNS

    picked = []
    codes = ("ui_ticker_column", "ui_date_column", "ui_price_column")
    for code, default in zip(codes, WAREHOUSE_COLUMNS):
        index = columns.index(default) if default in columns else 0
        # Keyed by the CODE, not by the translated label: the key is what carries the
        # user's choice across a re-run, and it must not move when the language does.
        picked.append(st.selectbox(text(code), columns, index=index, key=f"map_{code}"))
    return tuple(picked)


# --- The pieces of the page ---------------------------------------------------


def _prices(options: dict, loaded_frame):
    """The quote table and the three column names that describe it."""
    if options["prices_from"] == LOADED and loaded_frame is not None:
        return loaded_frame, options["columns"]
    return sources.from_database(options["connection"], QUOTES_QUERY), WAREHOUSE_COLUMNS


def _benchmark_frame(options: dict):
    """The rate series, from the BCB or from the warehouse, with the column names.

    Returns the frame AND the names of its two columns, because the two sources spell
    them differently (`data`/`valor` at the BCB, `date`/`value` in the database) and
    renaming one to look like the other would hide which source answered.
    """
    if options["live"]:
        frame = sources.from_bcb(options["benchmark_code"], options["start"], options["end"])
        return (frame, *BCB_COLUMNS)

    frame = sources.from_database(
        options["connection"], INDICATORS_QUERY, {"code": options["benchmark_code"]}
    )
    return (frame, *INDICATOR_COLUMNS)


def _workspace(frames: dict) -> None:
    """The downloaded tables, editable, exportable.

    `st.data_editor` and not `st.dataframe`: a series with a wrong day in it is a
    fact of life with public APIs, and the alternative to fixing it here is exporting,
    fixing in Excel and re-uploading. The edit stays in this session - the cache holds
    a copy, and the source is never written back to.
    """
    st.subheader(text("ui_workspace"))
    st.caption(text("ui_workspace_caption"))

    for name, frame in frames.items():
        with st.expander(text("ui_table_rows", name=name, rows=len(frame)), expanded=False):
            edited = st.data_editor(
                frame, num_rows="dynamic", use_container_width=True, key=f"edit_{name}"
            )
            st.download_button(
                text("ui_export", name=name),
                data=edited.to_csv(index=False).encode("utf-8"),
                file_name=f"{name}.csv",
                mime="text/csv",
                key=f"download_{name}",
            )


def _headline(scores, benchmark_return: float, universe: int) -> None:
    """The four numbers that answer "what am I looking at" before any scrolling."""
    best = scores[0]
    columns = st.columns(4)
    columns[0].metric(text("ui_benchmark_period"), f"{benchmark_return:.1%}")
    columns[1].metric(
        text("ui_best_premium"),
        best.ticker,
        delta=text("ui_vs_benchmark_delta", value=f"{best.excess_return:.1%}"),
    )
    columns[2].metric(
        text("ui_assets_ranked"), text("ui_count_of", count=len(scores), total=universe)
    )
    columns[3].metric(text("ui_trading_days"), best.days)


def _table(scores, names: dict) -> None:
    """The ranking itself. Every column that made the order is on screen."""
    st.dataframe(
        [
            {
                "#": position,
                text("ui_th_ticker"): score.ticker,
                text("ui_th_sector"): names.get(score.ticker, ""),
                text("ui_th_return"): f"{score.total_return:.1%}",
                text("ui_th_vs_benchmark"): f"{score.excess_return:+.1%}",
                text("ui_th_volatility"): f"{score.volatility:.1%}",
                text("ui_th_sharpe"): round(score.sharpe, 2),
                text("ui_th_worst_fall"): f"{score.max_drawdown:.1%}",
                "RSI": round(score.rsi, 0),
                text("ui_th_above_avg", window=ranking.TREND_WINDOW): (
                    text("ui_yes") if score.above_trend else text("ui_no")
                ),
            }
            for position, score in enumerate(scores, start=1)
        ],
        use_container_width=True,
        hide_index=True,
    )


def _why(score) -> None:
    """The leader, explained - in the language the session picked."""
    st.markdown(f"### {text('ui_why_first', ticker=score.ticker)}")
    st.caption(text("ui_why_caption"))
    for reason in score.reasons:
        st.write(f"- {translate(reason)}")


# --- The page -----------------------------------------------------------------


def render(connection: str, loaded_frame=None) -> None:
    """Draws the terminal.

    Args:
        connection: SQLAlchemy URL of the example warehouse - the default source of
            both the prices and the offline benchmark.
        loaded_frame: whatever the Explore tab currently has open, offered as an
            alternative price source. `None` when nothing is loaded there.
    """
    st.subheader(text("ui_search_ingest"))
    left, right = st.columns([2, 1])
    with left:
        query = st.text_input(
            text("ui_filter_assets"),
            placeholder="PETR4, VALE, AAPL...",
            help=text("ui_filter_assets_help"),
            key="term_query",
        )
    with right:
        uploads = st.file_uploader(
            text("ui_add_files"),
            accept_multiple_files=True,
            type=["csv", "json", "svg"],
            help=text("ui_add_files_help"),
            key="term_uploads",
        )

    available = [] if loaded_frame is None else [str(name) for name in loaded_frame.columns]
    options = _sources_form(connection, available)
    if options is None:
        st.info(text("ui_set_period_first"))
        return

    try:
        frame, columns = _prices(options, loaded_frame)
        panel = ranking.price_panel(frame, *columns)
        benchmark_frame, benchmark_date, benchmark_value = _benchmark_frame(options)
        benchmark = ranking.benchmark_series(
            benchmark_frame, benchmark_date, benchmark_value
        )
    except ConnectorError as error:
        # The BCB is down, or the database moved. One sentence, in the session's
        # language - a traceback here is the screen admitting it did not plan for it.
        st.error(translate(error.message))
        return
    except AnalysisError as error:
        st.error(translate(error.message))
        return

    period = (benchmark.index >= str(options["start"])) & (
        benchmark.index <= str(options["end"])
    )
    benchmark = benchmark[period]
    universe = panel["ticker"].nunique()

    names = _asset_names(options["connection"])
    if query.strip():
        panel = _filtered(panel, names, query.strip())

    tables = {"benchmark": benchmark_frame}
    for code in options["context_codes"]:
        try:
            tables[BCB_SERIES[code]["label"]] = sources.from_bcb(
                code, options["start"], options["end"]
            )
        except ConnectorError as error:
            st.warning(translate(error.message))

    for uploaded in uploads or []:
        if uploaded.name.lower().endswith(".svg"):
            st.image(uploaded.getvalue(), caption=uploaded.name, width=240)
            continue
        try:
            tables[uploaded.name] = sources.from_file(to_temporary_path(uploaded), uploaded.name)
        except ConnectorError as error:
            st.warning(translate(error.message))

    try:
        scores = ranking.rank(panel, benchmark, top=options["top"])
    except AnalysisError as error:
        st.error(translate(error.message))
        _workspace(tables)
        return

    _headline(scores, scores[0].benchmark_return, universe)
    st.subheader(text("ui_top", count=len(scores)))
    _table(scores, names)
    _why(scores[0])
    _workspace(tables)


def _asset_names(connection: str) -> dict:
    """Ticker to sector, for the table. A missing table is not worth an error here."""
    try:
        frame = sources.from_database(connection, ASSETS_QUERY)
    except ConnectorError:
        return {}
    return dict(zip(frame["ticker"], frame["sector"]))


def _filtered(panel, names: dict, query: str):
    """Keeps the tickers whose code or sector contains what was typed."""
    wanted = query.lower()
    keep = [
        ticker
        for ticker in panel["ticker"].unique()
        if wanted in str(ticker).lower() or wanted in str(names.get(ticker, "")).lower()
    ]
    return panel[panel["ticker"].isin(keep)]
