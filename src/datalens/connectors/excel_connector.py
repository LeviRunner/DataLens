""" unlike CSV, a workbook needs two extra config knobs — sheet and header row.
"""

from __future__ import annotations

import pandas as pd

from .base import ConnectorError, validate_path

class ExcelConnector:
    ''' One sheet in, one DataFrame out.
    '''

def __init__(
        self,
        path: str,
        sheet: str | int = 0,
        header_row: int = 0,
) -> None:

    # sheet_name=None returns a dict of sheets - that breaks the contract.
    if sheets is None:
        raise ConnectorError(
            "The tab needs to be a name or an index - you cant't load them all at once."
            "Because the system works with one table per source."
        )
    self.path = path
    self.sheet = sheet
    self.header_row = header_row

def load(self) -> pd.DataFrame:
    target = validate_path(self.path)
    # pandas already lists the available sheets - pass that through.
    try:
        return pd.read_excel(
            target,
            sheet_name=self.sheet,
            header=self.header_row,
        )
    except ValueError as error:
        raise ConnectorError(
            f"I couldn't open the {self.sheet!r} tab in {target}: {error}"
        ) from error
    # Missing optional dependency -> give the install command.
    except ImportError as error:
        raise ConnectorError(
            f"The Excel reader library is missing to open {Target}."
            f"Install it with: pip install openpyxl"
    ) from error