"""Reads JSON - from a file on disk or from a public URL - and returns a DataFrame.

TWO ORIGINS, ONE CONTRACT. `source` is either a path or an address. When it starts
with `http://` or `https://` the connector fetches it; otherwise it opens the file.
The caller never has to say which: there is no `is_url` flag to get wrong. What the
two universes MUST share is the failure: a missing file and a DNS that never resolved
both mean "there is no data", and both leave here as the same `ConnectorError`.

THE BORDER WITH api_connector.py: this connector has no API key, no query params and
no special treatment for 429. It is for JSON that is simply public - the file you
downloaded, the open endpoint of the Banco Central. The moment the source asks for
authentication, `APIConnector` is the right tool.

JSON IS NOT INHERENTLY TABULAR, which CSV never had to worry about. A file may hold a
list of rows, a payload with the rows buried under keys, one bare object, or something
that is not a table at all. Deciding what each shape becomes is the work of this module:

    [{...}, {...}]      -> one row each
    {...}               -> a single row
    []                  -> an empty DataFrame ("no rows" is a valid answer)
    42, [1, 2, 3]       -> refused; a nameless one-column frame would only push the
                           confusion downstream into the detector

THE CONNECTOR CONVERTS NOTHING. `"0.05"` and `"02/01/2026"` leave here exactly as they
arrived. The chain is connector -> detector (decides) -> cleaning (converts); inferring
a dtype here is already an opinion, and the opinion belongs to the detector.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .base import ConnectorError, validate_path

# Without a timeout `requests` waits forever: a source that is down freezes the whole
# app, which in Streamlit is a tab loading eternally, with no error and no data.
DEFAULT_TIMEOUT = 30

URL_SCHEMES = ("http://", "https://")


class JSONConnector:
    """Reads JSON from a local file or a public URL and returns it as a DataFrame.

    Args:
        source: a file path or an `http(s)` address. The prefix decides which.
        records_path: dotted path down to the list of records inside the payload,
            e.g. `"data.items"` for `{"data": {"items": [...]}}`. Leave empty when
            the payload already is the list (or the single object).
        encoding: how to decode the file on disk. Ignored for URLs, where the
            server declares it.
        lines: read JSON Lines - one JSON object per line, no enclosing list. It is
            what log exporters and data dumps produce, and a plain `json.loads`
            raises on it.
        timeout: seconds to wait before giving up on the request.

    Example:
        >>> JSONConnector("data/quotes.json").load()
        >>> JSONConnector("https://x.com/series", records_path="data.items").load()
    """

    def __init__(
        self,
        source: str | Path,
        records_path: str | None = None,
        encoding: str = "utf-8",
        lines: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.source = source
        self.records_path = records_path
        self.encoding = encoding
        self.lines = lines
        self.timeout = timeout

    # --- The contract ---------------------------------------------------------

    def load(self) -> pd.DataFrame:
        """Reads the source, digs out the records and builds the DataFrame."""
        payload = self._fetch() if self._is_url else self._read_file()
        records = self._extract_records(payload)

        # `json_normalize` and not `DataFrame` because JSON payloads nest:
        # {"price": {"open": 10}} becomes the column `price.open` instead of one
        # column holding a dict, which nothing downstream would know how to read.
        # It flattens structure - it does not convert values.
        return self._as_plain_objects(pd.json_normalize(records))

    @property
    def _is_url(self) -> bool:
        """The whole two-origin decision, in one line and in one place."""
        return str(self.source).lower().startswith(URL_SCHEMES)

    @staticmethod
    def _as_plain_objects(frame: pd.DataFrame) -> pd.DataFrame:
        """Keeps text columns as plain Python objects instead of a typed string column.

        pandas infers a `str` dtype for text on its own, and that inference is already
        a decision about the data - the one decision this connector is not allowed to
        make. Numeric columns keep the dtype pandas built them with.
        """
        text_columns = [
            column
            for column in frame.columns
            if isinstance(frame[column].dtype, pd.StringDtype)
        ]

        if not text_columns:
            return frame

        return frame.astype({column: object for column in text_columns})

    # --- Origin one: the disk -------------------------------------------------

    def _read_file(self) -> Any:
        """Opens the file, decodes it and turns the text into Python objects."""
        # `validate_path` first, so "file not found" reads the same here as it does
        # in the CSV and the Excel connectors.
        target = validate_path(self.source)

        try:
            text = target.read_bytes().decode(self.encoding)
        except UnicodeDecodeError as error:
            raise ConnectorError(
                "csv_encoding_failed", path=target, encoding=repr(self.encoding)
            ) from error

        # An empty file is NOT the same as `[]`: it means the download failed or the
        # export never ran. Returning zero rows silently would hide that.
        if not text.strip():
            raise ConnectorError("csv_empty_file", path=target)

        return self._parse(text, origin=target)

    # --- Origin two: the network ----------------------------------------------

    def _fetch(self) -> Any:
        """Requests the address and turns the answer into Python objects."""
        try:
            response = requests.get(str(self.source), timeout=self.timeout)
            # Without `raise_for_status` a 404 would travel on as a valid answer and
            # surface later as "not JSON", hiding the real cause.
            response.raise_for_status()

        # Subclasses before the base class, or they never run: Timeout, ConnectionError
        # and HTTPError are all RequestException, and the first matching clause wins.
        except requests.Timeout as error:
            raise ConnectorError("api_timeout", timeout=self.timeout) from error

        except requests.ConnectionError as error:
            raise ConnectorError("api_connection_failed", host=self.source) from error

        except requests.HTTPError as error:
            status = getattr(error.response, "status_code", None)
            raise ConnectorError("api_http_error", status=status) from error

        except requests.RequestException as error:
            raise ConnectorError("api_connection_failed", host=self.source) from error

        if self.lines:
            return self._parse(response.text, origin=self.source)

        # A maintenance page or a captive portal answers 200 with HTML, and the raw
        # `Expecting value: line 1 column 1` tells the user nothing.
        try:
            return response.json()
        except ValueError as error:
            raise ConnectorError("api_not_json", host=self.source) from error

    # --- Text into Python objects ---------------------------------------------

    def _parse(self, text: str, origin: Any) -> Any:
        """Decodes the text, keeping the position of the problem in the message."""
        if self.lines:
            return self._parse_lines(text, origin)

        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            # The likeliest mistake with a .jsonl file is forgetting the flag. Saying
            # "invalid JSON" there sends the user hunting for a syntax error that is
            # not present, so name the option instead.
            if self._looks_like_json_lines(text):
                raise ConnectorError("json_lines_expected", path=origin) from error

            # `json.JSONDecodeError` knows the line and the column. Passing that
            # through turns "invalid JSON" into something the user can go fix.
            raise ConnectorError(
                "json_invalid", path=origin, detail=str(error)
            ) from error

    def _parse_lines(self, text: str, origin: Any) -> list[Any]:
        """One JSON object per line - the shape log exporters and data dumps produce."""
        records: list[Any] = []

        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ConnectorError(
                    "json_invalid",
                    path=origin,
                    detail=f"line {number}: {error}",
                ) from error

        return records

    @staticmethod
    def _looks_like_json_lines(text: str) -> bool:
        """True when every non-blank line is valid JSON on its own."""
        lines = [line for line in text.splitlines() if line.strip()]

        if len(lines) < 2:
            return False

        for line in lines:
            try:
                json.loads(line)
            except json.JSONDecodeError:
                return False

        return True

    # --- Digging the records out ----------------------------------------------

    def _extract_records(self, payload: Any) -> Any:
        """Walks the dotted path down to the records and checks the shape is a table.

        Raises:
            ConnectorError: when `records_path` does not exist in the payload - the
                message names the path that was tried and the keys that do exist,
                because "path not found" is useless when the config has three paths
                in it - or when what sits at the end of it is not a table.
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

        # A bare object is not a list, but it IS one row. Rejecting it would be
        # pedantic; returning an empty frame would be worse.
        if isinstance(current, dict):
            return [current]

        if not isinstance(current, list) or not all(
            isinstance(item, dict) for item in current
        ):
            raise ConnectorError(
                "json_not_tabular", path=self.source, found=type(current).__name__
            )

        return current

    @staticmethod
    def _available_keys(node: Any) -> Any:
        """What the user could have written instead - keys, or the type when there are none."""
        return list(node) if isinstance(node, dict) else type(node).__name__
