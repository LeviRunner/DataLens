"""
shared contract - every source implements
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import pandas as pd

class ConnectorError(Exception):
    """ Failed to load data from any source.
    """

@runtime_checkable
class Connector(Protocol):
    """Any data source knows how to load itself into a DataFrame.
    """

    def load(self) -> pd.DataFrame:
        """It reads the source and returns the data in the system's unique format.
        """

def validate_path(path: str | Path) -> Path:
    """It verifies that the path points to a readable file and returns the 'Path'.
    """

    if not str(path).strip():
        raise ConnectorError("Empty file path - the connector doesn't know what to read.")

    target = Path(path)

    if not target.exists():
        raise ConnectorError(
            f"File not found: {target}."
            f"Check the path in the config (relative to {Path.cwd()})."
        )
    if not target.is_file():
        raise ConnectorError(f"{target} It's a directory, not a data file.")

    return target
