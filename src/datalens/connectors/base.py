"""The shared contract - every source implements it.

One exception type and one method. Everything downstream (detector, cleaning,
profiling) works against `pd.DataFrame` and never needs to know where it came from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import pandas as pd

from ..i18n import DataLensError


class ConnectorError(DataLensError):
    """Failed to load data from any source.

    One type for every origin - a missing file, a broken query and a DNS failure all
    mean the same thing to the caller: there is no data. Callers should never have to
    branch on which connector failed.

    Raised with a message code and its parameters, never with a sentence:

        raise ConnectorError("file_not_found", path=target, cwd=Path.cwd())

    `str(error)` gives the English text for the log; `translate(error.message)` gives
    the user's language for the screen.
    """


@runtime_checkable
class Connector(Protocol):
    """Any data source knows how to load itself into a DataFrame.

    A Protocol and not an abstract base class: a connector satisfies the contract by
    having the method, without importing or inheriting anything. That is what keeps
    the connectors independent of each other.
    """

    def load(self) -> pd.DataFrame:
        """Reads the source and returns the data in the system's single format."""


def validate_path(path: str | Path) -> Path:
    """Checks that the path points to a readable file and returns it as a `Path`.

    Shared by every file-based connector so that "file not found" reads the same
    whether the source was a CSV, a workbook or a JSON dump.
    """
    if not str(path).strip():
        raise ConnectorError("empty_path")

    target = Path(path)

    if not target.exists():
        raise ConnectorError("file_not_found", path=target, cwd=Path.cwd())
    if not target.is_file():
        raise ConnectorError("path_is_directory", path=target)

    return target
