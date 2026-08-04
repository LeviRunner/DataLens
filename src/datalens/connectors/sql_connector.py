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
            raise ConnectorError("sql_empty_connection")
        if not query or not query.strip():
            raise ConnectorError("sql_empty_query")

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
                "sql_invalid_connection", connection=repr(self.connection)
            ) from error

        try:
            with engine.connect() as open_connection:
                return pd.read_sql(
                    text(self.query), open_connection, params=self.parameters
                )
        except (SQLAlchemyError, pd.errors.DatabaseError) as error:
            raise ConnectorError(
                "sql_query_failed", connection=repr(self.connection), detail=error
            ) from error
        finally:
            engine.dispose()
