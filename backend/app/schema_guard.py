"""Safety guard for legacy request-time schema helpers.

RULE: the API database role may read and write rows but must NOT create, alter or drop tables.
Schema changes belong in numbered files in backend/schema (NNN_name.sql), which the deploy
process applies as the database owner after taking a backup.

Older modules still run CREATE/ALTER statements inside `_ensure*` helpers. Decorating those
helpers with @tolerate_missing_ddl_permission means a permission refusal is logged and skipped
(the tables are expected to exist already) instead of failing the whole request with a 500.
"""
import functools
import logging

import psycopg

logger = logging.getLogger("superbajaar.schema")


def tolerate_missing_ddl_permission(func):
    @functools.wraps(func)
    def wrapper(conn, *args, **kwargs):
        try:
            with conn.transaction():  # savepoint: a refused statement leaves no partial changes
                return func(conn, *args, **kwargs)
        except psycopg.errors.InsufficientPrivilege as exc:
            logger.warning(
                "%s skipped: API role cannot change schema (%s). "
                "Add the change as a numbered file in backend/schema instead.",
                func.__name__, str(exc).strip().splitlines()[0],
            )
            return None
    return wrapper
