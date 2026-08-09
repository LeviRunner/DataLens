"""Where the screens get their data, and the cache that keeps them from asking twice.

Both screens need the same three things - the warehouse, the Banco Central, an
uploaded file - and a Streamlit script re-runs from the top on every widget anyone
touches. Two copies of these loaders would mean two caches: the home page and the
terminal would each call the BCB for the same period, and neither would know the other
already had the answer. `st.cache_data` is keyed by function AND arguments, so one
definition shared by both screens is also one call.

`st.cache_data` hands every caller a COPY of the cached value, which is what makes the
editable workspace in the terminal safe - an edit cannot reach back into the cache.
(`st.cache_resource` shares one object and would not be.)

No query here has a JOIN, and that is deliberate: how the tables relate is the
database's business - a view - or the user's, in a query they wrote. A screen that
knows the joins breaks silently the day the schema moves.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from datalens.connectors.api_connector import APIConnector
from datalens.connectors.csv_connector import CSVConnector
from datalens.connectors.json_connector import JSONConnector
from datalens.connectors.sql_connector import SQLConnector

# --- What the Banco Central publishes -----------------------------------------
# The SGS is one endpoint with a number in the middle, and the number is the whole
# API. Each entry carries the sentence that goes on screen, because "series 11" means
# nothing to somebody who has not read the BCB manual.

BCB_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
BCB_DATE_FORMAT = "%d/%m/%Y"

# `daily_rate` marks the series that can BE a benchmark. The IPCA is monthly and the
# dollar is a price, not a rate - offering them as a benchmark would produce a number
# that formats beautifully and means nothing.
BCB_SERIES = {
    11: {
        "label": "Selic (SGS 11)",
        "daily_rate": True,
        "help": "Daily interest rate, in % per day. The cost of not investing.",
    },
    12: {
        "label": "CDI (SGS 12)",
        "daily_rate": True,
        "help": "Daily interbank rate, in % per day. The usual benchmark for funds.",
    },
    433: {
        "label": "IPCA (SGS 433)",
        "daily_rate": False,
        "help": "Monthly inflation, in % per month. Context only - not a daily benchmark.",
    },
    1: {
        "label": "USD/BRL (SGS 1)",
        "daily_rate": False,
        "help": "Exchange rate, a price and not a rate. Context only.",
    },
}

QUOTES_QUERY = "SELECT ticker, date, close FROM quotes"
ASSETS_QUERY = "SELECT ticker, name, sector, country FROM assets"
INDICATORS_QUERY = "SELECT date, value FROM indicators WHERE code = :code"

# The columns the warehouse spells its quotes with, and the ones the BCB spells its
# series with. Named because three files would otherwise each hold their own string.
WAREHOUSE_COLUMNS = ("ticker", "date", "close")
BCB_COLUMNS = ("data", "valor")
INDICATOR_COLUMNS = ("date", "value")

CACHE_SECONDS = 3600


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def from_bcb(code: int, start: date, end: date):
    """Downloads one SGS series. Cached: the same period is never asked twice.

    The dates travel as `params`, never pasted into the URL - `requests` escapes the
    slashes, and the connector keeps the key handling and the error messages that a
    hand-rolled `requests.get` here would have to reinvent worse.
    """
    return APIConnector(
        BCB_URL.format(code=code),
        params={
            "formato": "json",
            "dataInicial": start.strftime(BCB_DATE_FORMAT),
            "dataFinal": end.strftime(BCB_DATE_FORMAT),
        },
    ).load()


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def from_database(connection: str, query: str, parameters: dict | None = None):
    """Reads the example warehouse. Cached: the file does not change mid-session."""
    return SQLConnector(connection, query, parameters=parameters).load()


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def from_file(path: str, name: str):
    """Reads one uploaded table.

    `name` is in the signature so the cache key changes when the user uploads a
    different file that happens to land on the same temporary path.
    """
    if name.lower().endswith(".json"):
        return JSONConnector(path).load()
    return CSVConnector(path).load()
