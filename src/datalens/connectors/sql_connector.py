""" Bind parameters, never string interpolation - that is what stops SQL injection.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


from .base import ConnectorError


class SQLConnector:
    """ Executes the user's query in a database and returns the result as DataFrame.
    """

    def __init__(
        self,
        connection: str,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        if not connection or not connection.strip():
            raise ConnectorError("Empty connection string.")
        if not query or not query.strip():
            raise ConnectorError("Empty query - the SQL connector needs to know what to query.")

        self.connection = connection
        self.query = query
        self.parameters = parameters or {}

    def load(self) -> pd.DataFrame:
        """Open the connection, run the query, and return the result.
        """
        try:
            engine = create_engine(self.connection)
        except SQLAlchemyError as error:
            raise ConnectorError(
                f"Invalid connection string: {self.connection!r}. "
                f"Use the SQLAlchemy format, e.g., 'sqlite:///path/database.db'."
            ) from error

        try:
            with engine.connect() as call:
                return pd.read_sql(text(self.query), call, params=self.parameters)
        except (SQLAlchemyError, pd.errors.DatabaseError) as error:
            raise ConnectorError(
                f"Failed to execute query in {self.connection!r}: {error}"
            ) from error
        finally:
            engine.dispose()
