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

import sys
import tempfile
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
# The package lives under src/ and is not installed - the script has to say where it is
# before importing it, exactly like tests/conftest.py does.
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from datalens import charts, cleaning, detector, profiling  # noqa: E402
from datalens.config_loader import VALID_COLUMN_TYPES, ConfigError  # noqa: E402
from datalens.connectors.api_connector import APIConnector  # noqa: E402
from datalens.connectors.base import ConnectorError  # noqa: E402
from datalens.connectors.csv_connector import CSVConnector  # noqa: E402
from datalens.connectors.excel_connector import ExcelConnector  # noqa: E402
from datalens.connectors.sql_connector import SQLConnector  # noqa: E402
from datalens.i18n import (  # noqa: E402
    LANGUAGE_NAMES,
    SUPPORTED_LANGUAGES,
    set_language,
    translate,
)

EXAMPLES = _ROOT / "data" / "exemplos"
EXAMPLE_CSV = EXAMPLES / "acoes_b3.csv"
EXAMPLE_DB = f"sqlite:///{(EXAMPLES / 'finance.db').as_posix()}"

# The database already flattened the snowflake - the app only names the views.
READY_MADE_VIEWS = ("v_assets_full", "v_positions")
VIEW_QUERY = "SELECT * FROM {view}"

SOURCES = ("example", "csv", "excel", "sql", "api")
PREVIEW_ROWS = 50


# --- Reading the user's input -------------------------------------------------


def _uploaded_to_path(uploaded, suffix: str) -> str:
    """Connectors take a path; an upload lives in memory. This is the only bridge."""
    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temporary.write(uploaded.getvalue())
    temporary.close()
    return temporary.name


def _csv_connector():
    uploaded = st.sidebar.file_uploader("CSV file", type=["csv"])
    separator = st.sidebar.selectbox("Separator", (",", ";", "\t"))
    encoding = st.sidebar.selectbox("Encoding", ("utf-8", "latin-1"))
    decimal = st.sidebar.selectbox("Decimal mark", (".", ","))
    if uploaded is None:
        return None
    return CSVConnector(
        _uploaded_to_path(uploaded, ".csv"),
        separator=separator,
        encoding=encoding,
        decimal=decimal,
    )


def _excel_connector():
    uploaded = st.sidebar.file_uploader("Excel workbook", type=["xlsx", "xls"])
    sheet = st.sidebar.text_input("Sheet (name or index)", value="0")
    header_row = st.sidebar.number_input("Header row", min_value=0, value=0, step=1)
    if uploaded is None:
        return None
    return ExcelConnector(
        _uploaded_to_path(uploaded, ".xlsx"),
        sheet=int(sheet) if sheet.isdigit() else sheet,
        header_row=int(header_row),
    )


def _sql_connector():
    connection = st.sidebar.text_input("Connection string", value=EXAMPLE_DB)
    view = st.sidebar.selectbox("Ready-made view", ("(write my own query)",) + READY_MADE_VIEWS)
    suggested = "" if view.startswith("(") else VIEW_QUERY.format(view=view)
    query = st.sidebar.text_area("Query", value=suggested, height=110)
    if not connection.strip() or not query.strip():
        return None
    return SQLConnector(connection, query)


def _api_connector():
    url = st.sidebar.text_input("Endpoint URL")
    records_path = st.sidebar.text_input("Records path (optional)")
    api_key_env = st.sidebar.text_input("API key environment variable (optional)")
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
            f"{column} - guessed {guess.type} ({guess.confidence:.0%})",
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
                "column": item.column,
                "type": item.type,
                "values": item.count,
                "missing": item.missing,
                "missing %": round(item.missing_pct, 2),
            }
            for item in profiles.values()
        ],
        use_container_width=True,
    )


def _statistics_panel(profiles) -> None:
    column = st.selectbox("Column statistics", list(profiles), key="stats_column")
    stats = profiles[column].stats
    # str() on the value because a profile carries dates, lists and dicts, and the
    # table only has to be readable - no conversion rule belongs to this file.
    st.dataframe(
        [{"statistic": key, "value": str(value)} for key, value in stats.items()],
        use_container_width=True,
    )


def _distribution_panel(df, types) -> None:
    column = st.selectbox("Distribution of", list(df.columns), key="chart_column")
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

    st.subheader("Over time")
    date_column = st.selectbox("Date column", dates, key="ts_date")
    value_column = st.selectbox("Value column", numbers, key="ts_value")
    group_by = st.selectbox("One line per", ["(none)"] + groups, key="ts_group")
    try:
        figure = charts.time_series_chart(
            df,
            date_column,
            value_column,
            group_by=None if group_by == "(none)" else group_by,
        )
    except ValueError as error:
        # charts refuses to plot a column it cannot read as dates - say so, don't crash.
        st.warning(str(error))
        return
    st.plotly_chart(figure, use_container_width=True)


def _cleaning_log(log) -> None:
    if not log:
        st.info("Nothing to clean: no duplicates, no conversions, no missing values.")
        return
    st.dataframe(
        [
            {
                "column": action.column or "(all)",
                "action": action.action,
                "rows": action.count,
                "detail": action.detail or "",
            }
            for action in log
        ],
        use_container_width=True,
    )


# --- The page -----------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="DataLens", layout="wide")
    st.title("DataLens")

    language = st.sidebar.selectbox(
        "Language / Idioma",
        SUPPORTED_LANGUAGES,
        format_func=lambda code: LANGUAGE_NAMES[code],
    )
    # Per session, not per process: i18n keeps it in a ContextVar for this reason.
    set_language(language)

    source = st.sidebar.selectbox("Source", SOURCES)
    should_clean = st.sidebar.checkbox("Clean the data before profiling", value=False)

    try:
        connector = _connector_for(source)
        if connector is None:
            st.info("Choose a file or fill in the source fields on the left.")
            return
        df = connector.load()
    except (ConnectorError, ConfigError) as error:
        # One type caught, one sentence printed, in the language of this session.
        st.error(translate(error.message))
        return

    st.caption(f"{len(df)} rows, {len(df.columns)} columns")
    st.dataframe(df.head(PREVIEW_ROWS), use_container_width=True)

    with st.expander("Column types - correct any wrong guess", expanded=False):
        types = _corrected_types(df, detector.detect(df))

    if should_clean:
        df, log = cleaning.clean(df, types)
        st.subheader("What cleaning changed")
        _cleaning_log(log)

    profiles = profiling.profile(df, types)

    st.subheader("Profile")
    _profile_table(profiles)
    _statistics_panel(profiles)

    st.subheader("Distribution")
    _distribution_panel(df, types)
    _time_series_panel(df, types)


main()
