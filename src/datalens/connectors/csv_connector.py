"""Reads a CSV file specified in the configuration ans returns the data -
    in the system's unique format.
"""

from __future__ import annotations

import pandas as pd

from .base import ConnectorError, validate_path

class CSVConnector:
    """Reads a CSV file and transforms the content into a DataFrame
    """

def __init__(
        self,
        path: str,
        separator: str = ",",
        encoding: str = "utf-8",
        decimal: str = ".",
) -> None:
    self.path = path
    self.separator = separator
    self.encoding = encoding
    self.decimal = decimal

def load(self) -> pd.DataFrame:
    """ Reads the CSV and returns the DataFrame.
    """
    # validate the path first, then read.
    target = validate_path(self.path)

    try:
        return pd.read_csv(
            target,
            sep=self.separator,
            encoding=self.encoding,
            decimal=self.decimal,
        )
    
    # EN: encoding error -> suggest the fix ('latin-1').
    except UnicodeDecodeError as error:
        raise ConnectorError(
            f"I couldn't read {target} with encoding {self.encoding!r}."
            f"If the file came from Excel on Windows, try 'latin-1' in the configuration."
        ) from error

    # EN: empty file is not a config mistake — nothing to fix.

    except pd.errors.EmptyDataError as error:
        raise ConnectorError(
            f"The file {target} is empty - there is no data to read."
        ) from error

    # EN: ragged rows almost always mean the wrong separator.

    except pd.errors.ParserError as error:
        raise ConnectorError(
            f"I couldn't interpret the structure of {target} using the separator"
            f"{self.separator}. Check if the file uses ';' or tabulation"
        ) from error
