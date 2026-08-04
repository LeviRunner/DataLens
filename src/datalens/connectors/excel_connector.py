"""Unlike CSV, a workbook needs two extra config knobs — sheet and header row."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import ConnectorError, validate_path


class ExcelConnector:
    """One sheet in, one DataFrame out."""

    def __init__(
        self,
        path: str | Path,
        sheet: str | int | None = 0,
        header_row: int = 0,
    ) -> None:
        # sheet_name=None returns a dict of sheets - that breaks the contract.
        if sheet is None:
            raise ConnectorError("excel_all_sheets_refused")
        self.path = path
        self.sheet = sheet
        self.header_row = header_row

    def load(self) -> pd.DataFrame:
        """Reads one sheet and returns the DataFrame."""
        target = validate_path(self.path)

        try:
            return pd.read_excel(
                target,
                sheet_name=self.sheet,
                header=self.header_row,
            )
        # pandas already lists the available sheets - pass that through.
        except ValueError as error:
            # `detail` carries pandas' own text, which stays English on purpose: it is
            # a technical detail for the log, not the sentence that guides the user.
            raise ConnectorError(
                "excel_sheet_not_found",
                sheet=repr(self.sheet),
                path=target,
                detail=error,
            ) from error
        # Missing optional dependency -> give the install command.
        except ImportError as error:
            raise ConnectorError("excel_missing_library", path=target) from error
