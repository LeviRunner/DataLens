""" Bind parameters, never string interpolation - that is what stops SQL injection.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError, ResourceClosedError, SQLAlchemyError


from .base import ConnectorError

# In SQLite the pragma lives on the CONNECTION, not on the database file. SQLAlchemy
# keeps a pool, so the next query may come out of a different connection - running the
# pragma once after connect() buys the ILLUSION of referential integrity.
FOREIGN_KEY_PRAGMA = "PRAGMA foreign_keys = ON"

SQLITE_DIALECT = "sqlite"

# What SQLite says when a foreign key is broken; other drivers word it the same way.
FOREIGN_KEY_MARKER = "foreign key"

# Last-resort placeholder when the URL cannot even be parsed to be masked.
REDACTED = "***"


def mask_connection(connection: str) -> str:
    """Return the connection string with any password replaced by `***`.

    A connection string is a credential: `postgresql://user:secret@host/db` carries a
    password that would otherwise reach the structured log and the screen through the
    error parameters. SQLAlchemy already knows how to render a URL without its
    password, so parsing is preferred over a regular expression - and anything that
    fails to parse is redacted whole rather than shown raw.
    """
    try:
        return make_url(connection).render_as_string(hide_password=True)
    except Exception:  # noqa: BLE001 - an unparseable URL must never be echoed back
        return REDACTED if "@" in connection else connection


def _is_foreign_key_violation(error: BaseException) -> bool:
    """Walk the `__cause__` chain looking for a broken foreign key.

    pandas wraps the SQLAlchemy error, which wraps the driver error, so the useful
    type is never the one that was caught.
    """
    current: BaseException | None = error
    while current is not None:
        is_integrity = isinstance(current, IntegrityError) or type(
            current
        ).__name__.endswith("IntegrityError")
        if is_integrity and FOREIGN_KEY_MARKER in str(current).lower():
            return True
        current = current.__cause__
    return False


class SQLConnector:
    """ Executes the user's query in a database and returns the result as DataFrame.
    """

    def __init__(
        self,
        connection: str,
        query: str,
        parameters: dict[str, Any] | None = None,
        foreign_keys: bool = True,
    ) -> None:
        if not connection or not connection.strip():
            raise ConnectorError("sql_empty_connection")
        if not query or not query.strip():
            raise ConnectorError("sql_empty_query")

        self.connection = connection
        self.query = query
        self.parameters = parameters or {}
        # Default ON: the safe path is the one you get without having to ask for it.
        # `False` stays a legitimate choice for bulk loading, where the rows arrive
        # out of dependency order and integrity is checked once at the end.
        self.foreign_keys = foreign_keys

    @property
    def safe_connection(self) -> str:
        """The connection string as it may be shown - never carries the password."""
        return mask_connection(self.connection)

    def _enforce_foreign_keys(self, engine: Engine) -> None:
        """Turn the pragma on for EVERY connection this engine hands out.

        Only for SQLite: in PostgreSQL or MySQL the pragma does not exist and the
        statement would break every connection instead of protecting it.
        """
        if not self.foreign_keys or engine.dialect.name != SQLITE_DIALECT:
            return

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record) -> None:
            dbapi_connection.execute(FOREIGN_KEY_PRAGMA)

    def load(self) -> pd.DataFrame:
        """Open the connection, run the query, and return the result.
        """
        try:
            engine = create_engine(self.connection)
            self._enforce_foreign_keys(engine)
        except (SQLAlchemyError, ImportError) as error:
            # ImportError too: a missing driver is still "this connection string does
            # not work here", and the module promises a ConnectorError, not a stack trace.
            raise ConnectorError(
                "sql_invalid_connection", connection=repr(self.safe_connection)
            ) from error

        try:
            with engine.connect() as open_connection:
                try:
                    return pd.read_sql(
                        text(self.query), open_connection, params=self.parameters
                    )
                except ResourceClosedError:
                    # The statement ran; it just returns no rows (INSERT, UPDATE, DDL).
                    # Committing here is what makes the write outlive the connection.
                    open_connection.commit()
                    return pd.DataFrame()
        except (SQLAlchemyError, pd.errors.DatabaseError) as error:
            if _is_foreign_key_violation(error):
                raise ConnectorError(
                    "sql_foreign_key_violation",
                    connection=repr(self.safe_connection),
                    detail=error,
                ) from error
            raise ConnectorError(
                "sql_query_failed", connection=repr(self.safe_connection), detail=error
            ) from error
        finally:
            engine.dispose()
