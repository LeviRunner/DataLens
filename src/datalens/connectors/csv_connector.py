"""Reads a CSV file specified in the configuration and returns the data -
    in the system's unique format.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import ConnectorError, validate_path


class CSVConnector:
    """Reads a CSV file and transforms the content into a DataFrame."""

    def __init__(
        self,
        path: str | Path,
        separator: str = ",",
        encoding: str = "utf-8",
        decimal: str = ".",
    ) -> None:
        self.path = path
        self.separator = separator
        self.encoding = encoding
        self.decimal = decimal

    def load(self) -> pd.DataFrame:
        """Reads the CSV and returns the DataFrame."""
        # validate the path first, then read.
        target = validate_path(self.path)

        try:
            return pd.read_csv(
                target,
                sep=self.separator,
                encoding=self.encoding,
                decimal=self.decimal,
            )

        # Encoding error -> suggest the fix ('latin-1').
        except UnicodeDecodeError as error:
            raise ConnectorError(
                "csv_encoding_failed", path=target, encoding=repr(self.encoding)
            ) from error

        # An empty file is not a config mistake — nothing to fix.
        except pd.errors.EmptyDataError as error:
            raise ConnectorError("csv_empty_file", path=target) from error

        # Ragged rows almost always mean the wrong separator.
        except pd.errors.ParserError as error:
            raise ConnectorError(
                "csv_parse_failed", path=target, separator=repr(self.separator)
            ) from error
