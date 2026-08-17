"""The DataLens screen: read input, call `src/datalens/`, draw the answer.

This file is deliberately thin. It owns no rule about the data - not how a type is
guessed, not how a column is cleaned, not how tables relate to each other. Every
question of that kind is answered by a module under `src/datalens/`, which is testable,
reusable by the CLI and by the HTML report. What lives here is widgets and layout.

Two consequences worth naming:
  * errors arrive as `ConnectorError`/`ConfigError` and are printed as ONE sentence
    through `translate(error.message)` - a traceback on screen is the app admitting it
    did not plan for that case;
  * the snowflake schema is flattened by the database, not here: `v_assets_full` and
    `v_positions` are offered as ready-made queries so nobody has to write ten joins,
    and no SQL is assembled by this file.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
# The package lives under src/ and is not installed - the script has to say where it is
# before importing it, exactly like tests/conftest.py does. `_HERE` goes in too so the
# sibling screens import the same way whether Streamlit or a test started the script.
for _path in (_ROOT / "src", _HERE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import downloader  # noqa: E402
import home  # noqa: E402
import terminal  # noqa: E402
import theme  # noqa: E402
from uploads import to_temporary_path  # noqa: E402

from datalens import charts, cleaning, detector, profiling  # noqa: E402
from datalens.config_loader import VALID_COLUMN_TYPES, ConfigError  # noqa: E402
from datalens.connectors.api_connector import APIConnector  # noqa: E402
from datalens.connectors.base import ConnectorError  # noqa: E402
from datalens.connectors.csv_connector import CSVConnector  # noqa: E402
from datalens.connectors.excel_connector import ExcelConnector  # noqa: E402
from datalens.connectors.sql_connector import SQLConnector  # noqa: E402
from datalens.i18n import (  # noqa: E402
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    set_language,
    text,
    translate,
    translator,
)

EXAMPLES = _ROOT / "data" / "exemplos"
EXAMPLE_CSV = EXAMPLES / "acoes_b3.csv"

# A variável de ambiente existe pelos TESTES, e por uma razão que o `conftest.py` já
# tinha escrito: "os testes são donos dos seus dados; nunca tocam em
# data/exemplos/finance.db". Os testes de fumaça da tela violavam isso desde sempre —
# sem consequência enquanto o banco tinha 12 ativos e 2 MB. Com 827 ativos e 134 MB,
# cada `AppTest.run()` passou a ler um milhão de cotações e a suíte estourou dois
# minutos. Apontar o app para um banco pequeno devolve os testes ao contrato.
EXAMPLE_DB_FILE = Path(os.environ.get("DATALENS_DB") or (EXAMPLES / "finance.db"))
EXAMPLE_DB = "duckdb"

# The database already flattened the snowflake - the app only names the views.
READY_MADE_VIEWS = ("v_assets_full", "v_positions")
VIEW_QUERY = "SELECT * FROM {view}"
OWN_QUERY = ""  # the "write it yourself" option, identified by a value, not by a label

SOURCES = ("example", "csv", "excel", "sql", "api")
PREVIEW_ROWS = 50

BRAND = "DATALENS"
BRAND_MARK = "◈"

# The menu. Home first because it is the one page that answers without being asked
# anything; the other two need a source or a period before they can say a word.
#
# THESE ARE IDENTIFIERS, NOT LABELS. Every string on screen is looked up in the i18n
# catalog at draw time, so the radio shows "Início" in Portuguese while `page == HOME`
# still compares "Home". Translating the value instead would make the branch below
# depend on the language, and the Terminal would stop opening in Spanish.
HOME = "Home"
EXPLORE = "Explore"
TERMINAL = "Terminal"
PAGES = (HOME, EXPLORE, TERMINAL)


# --- Reading the user's input -------------------------------------------------


def _csv_connector():
    # EVERY WIDGET HERE CARRIES AN EXPLICIT `key`. Streamlit identifies a widget by its
    # label when none is given, so a translated label is a NEW widget: switching to
    # Spanish would silently reset the separator, the encoding and the uploaded file.
    # The key is the identifier; the label is only what it says.
    uploaded = st.sidebar.file_uploader(text("ui_csv_file"), type=["csv"], key="csv_file")
    separator = st.sidebar.selectbox(text("ui_separator"), (",", ";", "\t"), key="csv_sep")
    encoding = st.sidebar.selectbox(text("ui_encoding"), ("utf-8", "latin-1"), key="csv_enc")
    decimal = st.sidebar.selectbox(text("ui_decimal"), (".", ","), key="csv_dec")
    if uploaded is None:
        return None
    return CSVConnector(
        to_temporary_path(uploaded),
        separator=separator,
        encoding=encoding,
        decimal=decimal,
    )


def _excel_connector():
    uploaded = st.sidebar.file_uploader(
        text("ui_excel_file"), type=["xlsx", "xls"], key="xls_file"
    )
    sheet = st.sidebar.text_input(text("ui_sheet"), value="0", key="xls_sheet")
    header_row = st.sidebar.number_input(
        text("ui_header_row"), min_value=0, value=0, step=1, key="xls_header"
    )
    if uploaded is None:
        return None
    return ExcelConnector(
        to_temporary_path(uploaded),
        sheet=int(sheet) if sheet.isdigit() else sheet,
        header_row=int(header_row),
    )


def _sql_connector():
    connection = st.sidebar.text_input(
        text("ui_connection_string"), value=EXAMPLE_DB, key="sql_conn"
    )
    # `OWN_QUERY` is an empty identifier and not the sentence "(write my own query)":
    # the sentence changes with the language, and a branch that tests it would stop
    # recognising the option the moment the user picks Portuguese.
    label = translator()
    view = st.sidebar.selectbox(
        text("ui_ready_made_view"),
        (OWN_QUERY,) + READY_MADE_VIEWS,
        format_func=lambda name: label("ui_own_query") if name == OWN_QUERY else name,
        key="sql_view",
    )
    suggested = "" if view == OWN_QUERY else VIEW_QUERY.format(view=view)
    query = st.sidebar.text_area(text("ui_query"), value=suggested, height=110, key="sql_query")
    if not connection.strip() or not query.strip():
        return None
    return SQLConnector(connection, query)


def _api_connector():
    url = st.sidebar.text_input(text("ui_endpoint_url"), key="api_url")
    records_path = st.sidebar.text_input(text("ui_records_path"), key="api_records")
    api_key_env = st.sidebar.text_input(text("ui_api_key_env"), key="api_key_env")
    if not url.strip():
        return None
    return APIConnector(
        url,
        records_path=records_path or None,
        api_key_env=api_key_env or None,
    )


def _connector_for(source: str):
    """One connector per source, or None while the user has not supplied enough."""
    if source == "example":
        return CSVConnector(str(EXAMPLE_CSV))
    builders = {
        "csv": _csv_connector,
        "excel": _excel_connector,
        "sql": _sql_connector,
        "api": _api_connector,
    }
    return builders[source]()


# --- Drawing ------------------------------------------------------------------


def _corrected_types(df, guesses):
    """Shows the guess per column and lets the user overrule it.

    The vocabulary is the detector's own (numeric|date|boolean|category|text), so the
    correction goes straight back into `profile`, `clean` and the charts.
    """
    corrected = {}
    for column, guess in guesses.items():
        chosen = st.selectbox(
            text(
                "ui_guessed",
                column=column,
                type=guess.type,
                confidence=f"{guess.confidence:.0%}",
            ),
            VALID_COLUMN_TYPES,
            index=VALID_COLUMN_TYPES.index(guess.type),
            key=f"type_{column}",
        )
        corrected[column] = detector.DetectedType(
            column=column, type=chosen, confidence=guess.confidence
        )
    return corrected


def _profile_table(profiles) -> None:
    st.dataframe(
        [
            {
                text("ui_th_column"): item.column,
                text("ui_th_type"): item.type,
                text("ui_th_values"): item.count,
                text("ui_th_missing"): item.missing,
                text("ui_th_missing_pct"): round(item.missing_pct, 2),
            }
            for item in profiles.values()
        ],
        use_container_width=True,
    )


def _statistics_panel(profiles) -> None:
    column = st.selectbox(text("ui_column_statistics"), list(profiles), key="stats_column")
    stats = profiles[column].stats
    # str() on the value because a profile carries dates, lists and dicts, and the
    # table only has to be readable - no conversion rule belongs to this file.
    st.dataframe(
        [
            {text("ui_th_statistic"): key, text("ui_th_value"): str(value)}
            for key, value in stats.items()
        ],
        use_container_width=True,
    )


def _distribution_panel(df, types) -> None:
    column = st.selectbox(text("ui_distribution_of"), list(df.columns), key="chart_column")
    st.plotly_chart(
        charts.distribution_chart(df, column, types[column].type),
        use_container_width=True,
    )


def _time_series_panel(df, types) -> None:
    dates = [name for name, guess in types.items() if guess.type == "date"]
    numbers = [name for name, guess in types.items() if guess.type == "numeric"]
    groups = [name for name, guess in types.items() if guess.type == "category"]
    if not dates or not numbers:
        return

    st.subheader(text("ui_over_time"))
    date_column = st.selectbox(text("ui_date_column"), dates, key="ts_date")
    value_column = st.selectbox(text("ui_value_column"), numbers, key="ts_value")
    # `None` is the "no grouping" option, and it is the VALUE - the sentence next to it
    # is drawn by `format_func`, so switching language cannot turn the option into an
    # unrecognised column name.
    label = translator()
    group_by = st.selectbox(
        text("ui_one_line_per"),
        [None] + groups,
        format_func=lambda name: label("ui_none") if name is None else name,
        key="ts_group",
    )
    try:
        figure = charts.time_series_chart(df, date_column, value_column, group_by=group_by)
    except ValueError as error:
        # charts refuses to plot a column it cannot read as dates - say so, don't crash.
        st.warning(str(error))
        return
    st.plotly_chart(figure, use_container_width=True)


def _cleaning_log(log) -> None:
    if not log:
        st.info(text("ui_nothing_to_clean"))
        return
    st.dataframe(
        [
            {
                text("ui_th_column"): action.column or text("ui_all"),
                text("ui_th_action"): action.action,
                text("ui_th_rows"): action.count,
                text("ui_th_detail"): action.detail or "",
            }
            for action in log
        ],
        use_container_width=True,
    )


# --- The page -----------------------------------------------------------------


def _explore(df, should_clean: bool) -> None:
    """The profiling screen: what is in this table, column by column."""
    st.caption(text("ui_rows_columns", rows=len(df), columns=len(df.columns)))
    st.dataframe(df.head(PREVIEW_ROWS), use_container_width=True)

    with st.expander(text("ui_column_types"), expanded=False):
        types = _corrected_types(df, detector.detect(df))

    if should_clean:
        df, log = cleaning.clean(df, types)
        st.subheader(text("ui_cleaning_changed"))
        _cleaning_log(log)

    profiles = profiling.profile(df, types)

    st.subheader(text("ui_profile"))
    _profile_table(profiles)
    _statistics_panel(profiles)

    st.subheader(text("ui_distribution"))
    _distribution_panel(df, types)
    _time_series_panel(df, types)


def main() -> None:
    st.set_page_config(page_title="DataLens", layout="wide", initial_sidebar_state="expanded")
    theme.apply()

    # Language is read BEFORE any label is drawn: the menu above the switcher has to
    # come out in the session's language, and a clicked button is already in
    # session_state at the top of this very run.
    language = st.session_state.get("language", DEFAULT_LANGUAGE)
    for code in SUPPORTED_LANGUAGES:
        if st.session_state.get(f"lang_{code}"):
            language = code
    st.session_state["language"] = language
    set_language(language)

    theme.brand(BRAND, BRAND_MARK)

    # ONE page at a time, and not tabs. Tabs render every panel on every re-run - the
    # ranking would recompute while somebody is reading the profile - and they put a
    # second row of navigation above content that has to start at the top of the fold.
    # Bound once, here, and handed to every `format_func` below: see `i18n.translator`.
    label = translator()

    st.sidebar.markdown(f"**{text('ui_main_menu')}**")
    page = st.sidebar.radio(
        "Page",
        PAGES,
        format_func=lambda name: label(f"ui_page_{name}"),
        label_visibility="collapsed",
        key="page",
    )

    theme.language_buttons(language)

    # O CACHE GUARDA POR UMA HORA...
    if st.sidebar.button(
        text("ui_reload_data"), help=text("ui_reload_data_help"), use_container_width=True
    ):
        st.cache_data.clear()
        st.rerun()

    downloader.sidebar_button()

    start_time = time.time()

    with st.spinner("Carregando / Loading..."):
        if page == HOME:
            home.render(EXAMPLE_DB)
        else:
            source = st.sidebar.selectbox(
                text("ui_source"),
                SOURCES,
                format_func=lambda name: label(f"ui_source_{name}"),
                key="source",
            )
            should_clean = st.sidebar.checkbox(text("ui_clean_first"), value=False, key="clean")

            df = None
            error_message = None
            try:
                connector = _connector_for(source)
                df = None if connector is None else connector.load()
            except (ConnectorError, ConfigError) as error:
                error_message = translate(error.message)

            theme.page_title(page)

            if page == TERMINAL:
                terminal.render(EXAMPLE_DB, loaded_frame=df)
            elif error_message:
                st.error(error_message)
            elif df is None:
                st.info(text("ui_pick_a_source"))
            else:
                _explore(df, should_clean)

    theme.response_time(time.time() - start_time)


main()