"""Reads JSON from an HTTP API and returns the data in the system's single format.

What makes this connector different from the file-based ones is that the source lives
outside the machine: it can be slow, drop halfway, answer 500, or change shape without
warning. So it handles more failure modes than its siblings, and each one carries a
message code the user can act on.

SECRETS - the point of attention here:
    An API key never goes into the code and never into `config.yaml` (which is
    versioned). The connector takes `api_key_env`, the NAME of an environment variable,
    and reads the value with `os.environ` at load time.

    The messages raised here never carry the full URL, the query parameters or the
    headers - those are exactly the three places a key would be hiding. They carry the
    HOST only. That matters twice over since i18n: `str(error)` is one leak surface,
    and `error.message.params` - which feeds the structured log and the screen - is the
    other.

THE CONNECTOR CONVERTS NOTHING. The SGS endpoint of the Banco Central answers
`[{"data": "02/01/2026", "valor": "0.052"}]` - a dd/mm/yyyy date and a number as a
string - and that is how it must stay. The chain is connector -> detector (decides) ->
cleaning (converts); converting here would spread the conversion rule across five
connectors, each getting `1.234,56` wrong in its own way.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

import pandas as pd
import requests

from .base import ConnectorError

# Without a timeout `requests` waits forever: an API that is down freezes the whole app,
# which in Streamlit is a tab loading eternally, with no error and no data.
DEFAULT_TIMEOUT = 30

# 429 gets a code of its own, apart from `api_http_error`: a 404 and a 429 ask for
# opposite actions (check the address / wait), and one message serving both serves
# neither.
RATE_LIMITED_STATUS = 429


class APIConnector:
    """Fetches JSON from an HTTP API and returns it as a DataFrame.

    Args:
        url: the endpoint address. Query values do NOT belong here - see `params`.
        records_path: dotted path to the list of records inside the payload, e.g.
            `"data.items"` for `{"data": {"items": [...]}}`. Leave empty when the
            answer already is a list.
        api_key_env: the NAME of the environment variable holding the API key, never
            the key itself. It is read with `os.environ` at load time.
        timeout: seconds to wait before giving up on the request.
        params: query string values, sent through `requests` so that slashes, commas
            and accents get escaped by the library that knows how. Same reasoning as a
            SQL bind parameter: the value travels apart from the text.

    Example:
        >>> connector = APIConnector(
        ...     "https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados",
        ...     params={"formato": "json"},
        ... )
        >>> frame = connector.load()
    """

    def __init__(
        self,
        url: str,
        records_path: str | None = None,
        api_key_env: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.url = url
        self.records_path = records_path
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.params = params

    # --- The contract ---------------------------------------------------------

    def load(self) -> pd.DataFrame:
        """Requests the endpoint, digs out the records and builds the DataFrame."""
        headers = self._authentication_headers()
        response = self._request(headers)
        payload = self._parse_json(response)
        records = self._extract_records(payload)

        # `json_normalize` and not `DataFrame` because API payloads nest:
        # {"price": {"open": 10, "close": 12}} becomes the columns `price.open` and
        # `price.close` instead of one column holding a dict, which nothing downstream
        # would know how to read. It flattens structure - it does not convert values.
        return self._as_plain_objects(pd.json_normalize(records))

    @staticmethod
    def _as_plain_objects(frame: pd.DataFrame) -> pd.DataFrame:
        """Keeps text columns as plain Python objects instead of a typed string column.

        pandas infers a `str` dtype for text on its own, and that inference is already a
        decision about the data - the one decision this connector is not allowed to
        make. `"0.052"` and `"02/01/2026"` leave here exactly as they arrived, and the
        detector is what gets to have an opinion about them. Numeric columns keep the
        dtype pandas built them with.
        """
        text_columns = [
            column for column in frame.columns
            if isinstance(frame[column].dtype, pd.StringDtype)
        ]

        if not text_columns:
            return frame

        return frame.astype({column: object for column in text_columns})

    # --- The API key ----------------------------------------------------------

    def _authentication_headers(self) -> dict[str, str]:
        """Reads the key from the environment, failing with the variable's NAME.

        Failing here rather than letting the server answer 401 is what makes the
        message actionable: the name is the one thing that tells the user which
        `export` to write.
        """
        if not self.api_key_env:
            return {}

        key = os.environ.get(self.api_key_env)
        if not key:
            raise ConnectorError("api_missing_env_key", variable=self.api_key_env)

        return {"Authorization": f"Bearer {key}"}

    # --- The request ----------------------------------------------------------

    @property
    def _host(self) -> str:
        """The host alone - the only piece of the address safe to put in a message.

        `urlsplit(...).hostname` drops any `user:password@` prefix as well as the path
        and the query string, so a key pasted anywhere into the URL cannot ride along
        into a log line.
        """
        return urlsplit(self.url).hostname or ""

    def _request(self, headers: dict[str, str]) -> requests.Response:
        """Calls the API and returns the response, HTTP status already checked."""
        try:
            response = requests.get(
                self.url,
                params=self.params,
                headers=headers,
                timeout=self.timeout,
            )
            # Without `raise_for_status` a 404 or a 500 would travel on as a valid
            # answer and surface later as "not JSON", hiding the real cause.
            response.raise_for_status()
            return response

        # Subclasses before the base class, or they never run: Timeout, ConnectionError
        # and HTTPError are all RequestException, and the first matching clause wins.
        except requests.Timeout as error:
            raise ConnectorError("api_timeout", timeout=self.timeout) from error

        except requests.ConnectionError as error:
            raise ConnectorError("api_connection_failed", host=self._host) from error

        except requests.HTTPError as error:
            status = getattr(error.response, "status_code", None)

            if status == RATE_LIMITED_STATUS:
                raise ConnectorError("api_rate_limited") from error

            raise ConnectorError("api_http_error", status=status) from error

        except requests.RequestException as error:
            raise ConnectorError("api_connection_failed", host=self._host) from error

    def _parse_json(self, response: requests.Response) -> Any:
        """Turns the response body into Python objects.

        A maintenance page or a captive portal answers 200 with HTML, and the raw
        `Expecting value: line 1 column 1` tells the user nothing.
        """
        try:
            return response.json()
        except ValueError as error:
            raise ConnectorError("api_not_json", host=self._host) from error

    # --- Digging the records out ---------------------------------------------

    def _extract_records(self, payload: Any) -> Any:
        """Walks the dotted path down to the list of records and returns it.

        Raises:
            ConnectorError: when `records_path` does not exist in the answer, or what
                sits at the end of it is not a list of records. The message names the
                path that was tried and the keys that do exist - "path not found" is
                useless when four APIs call the same thing `results`, `data`, `items`
                and `records`.
        """
        current = payload
        path = self.records_path or ""

        for level in filter(None, path.split(".")):
            if not isinstance(current, dict) or level not in current:
                raise ConnectorError(
                    "api_records_path_not_found",
                    records_path=path,
                    available=self._available_keys(current),
                )
            current = current[level]

        # A single object (one quote instead of a list) is one row - wrapping it beats
        # making the user edit the config over it.
        if isinstance(current, dict):
            return [current]

        if not isinstance(current, list):
            raise ConnectorError(
                "api_records_path_not_found",
                records_path=path,
                available=self._available_keys(current),
            )

        return current

    @staticmethod
    def _available_keys(node: Any) -> Any:
        """What the user could have written instead - keys, or the type when there are none."""
        return list(node) if isinstance(node, dict) else type(node).__name__
