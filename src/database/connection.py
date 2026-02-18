"""
pg8000 connection manager with pooling and retry.
Reads DB_HOST, DB_NAME, DB_PORT, DB_USER, DB_PASSWORD from environment.
"""

import os
import time
import logging
from typing import Optional

import pg8000.native

logger = logging.getLogger(__name__)

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "f1_strategy")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_USER = os.environ.get("DB_USER", "f1_api")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

_MAX_RETRIES = 3
_RETRY_DELAY = 2.0
_POOL_SIZE = 5


def _create_connection() -> pg8000.native.Connection:
    """Create a new database connection with retry logic."""
    for attempt in range(_MAX_RETRIES):
        try:
            conn = pg8000.native.Connection(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                ssl_context=True,
            )
            return conn
        except Exception as exc:
            if attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAY * (attempt + 1)
                logger.warning(
                    "DB connection attempt %d/%d failed: %s. Retrying in %.1fs…",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                time.sleep(delay)
            else:
                raise RuntimeError(
                    f"Failed to connect to {DB_HOST}:{DB_PORT}/{DB_NAME} "
                    f"after {_MAX_RETRIES} attempts"
                ) from exc


class ConnectionPool:
    """Simple thread-unsafe pool suitable for single-threaded ingestion jobs."""

    def __init__(self, size: int = _POOL_SIZE) -> None:
        self._size = size
        self._pool: list[pg8000.native.Connection] = []
        for _ in range(size):
            self._pool.append(_create_connection())
        logger.info("Connection pool initialised with %d connections", size)

    def get(self) -> pg8000.native.Connection:
        if self._pool:
            conn = self._pool.pop()
            try:
                conn.run("SELECT 1")
                return conn
            except Exception:
                logger.warning("Stale connection detected; replacing.")
                return _create_connection()
        return _create_connection()

    def put(self, conn: pg8000.native.Connection) -> None:
        if len(self._pool) < self._size:
            self._pool.append(conn)
        else:
            try:
                conn.close()
            except Exception:
                pass

    def close_all(self) -> None:
        for conn in self._pool:
            try:
                conn.close()
            except Exception:
                pass
        self._pool.clear()


_pool: Optional[ConnectionPool] = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool()
    return _pool


class ManagedConnection:
    """Context manager that borrows a connection from the pool."""

    def __init__(self) -> None:
        self._conn: Optional[pg8000.native.Connection] = None

    def __enter__(self) -> pg8000.native.Connection:
        self._conn = get_pool().get()
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._conn is not None:
            if exc_type is not None:
                try:
                    self._conn.run("ROLLBACK")
                except Exception:
                    pass
            get_pool().put(self._conn)
            self._conn = None
        return False
