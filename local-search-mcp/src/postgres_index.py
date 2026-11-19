"""Persist file metadata in PostgreSQL."""

import hashlib
import json
import logging
import socket
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import IsolationLevel
from psycopg.rows import dict_row

from indexer import IndexChanges, IndexedFile, build_index, compare_index, is_within


logger = logging.getLogger(__name__)


class PostgresIndexError(RuntimeError):
    """A PostgreSQL operation on the file index failed."""


class PostgresIndex:
    def __init__(self, dsn: str, roots: tuple[Path, ...]):
        self.dsn = dsn
        self.roots = roots
        identity = json.dumps([socket.gethostname(), [str(root) for root in roots]])
        digest = hashlib.sha256(identity.encode("utf-8")).digest()
        self.catalog_id = digest.hex()
        self.lock_id = int.from_bytes(digest[:8], byteorder="big", signed=True)

    def refresh(self) -> tuple[int, IndexChanges]:
        """Scan the authorized folders and apply only changes to the catalog."""
        try:
            with psycopg.connect(self.dsn, connect_timeout=5, row_factory=dict_row) as connection:
                connection.isolation_level = IsolationLevel.READ_COMMITTED
                connection.execute("SELECT pg_advisory_xact_lock(%s::bigint)", (self.lock_id,))
                previous = self._read_catalog(connection)
                current = {item.path: item for item in build_index(self.roots)}
                changes = compare_index(previous, current)
                if changes["removed"]:
                    connection.execute(
                        "DELETE FROM local_search.indexed_files WHERE catalog_id = %s AND path = ANY(%s)",
                        (self.catalog_id, changes["removed"]),
                    )
                rows = [
                    {
                        **asdict(current[path]),
                        "catalog_id": self.catalog_id,
                        "modified_at": datetime.fromisoformat(current[path].modified_at),
                    }
                    for path in (*changes["new"], *changes["modified"])
                ]
                if rows:
                    with connection.cursor() as cursor:
                        cursor.executemany(
                            """
                            INSERT INTO local_search.indexed_files
                                (catalog_id, path, name, extension, size_bytes, modified_at, root)
                            VALUES
                                (%(catalog_id)s, %(path)s, %(name)s, %(extension)s,
                                 %(size_bytes)s, %(modified_at)s, %(root)s)
                            ON CONFLICT (catalog_id, path) DO UPDATE SET
                                name = EXCLUDED.name,
                                extension = EXCLUDED.extension,
                                size_bytes = EXCLUDED.size_bytes,
                                modified_at = EXCLUDED.modified_at,
                                root = EXCLUDED.root
                            """,
                            rows,
                        )
        except psycopg.Error as error:
            logger.error("PostgreSQL index write failed (%s).", type(error).__name__)
            raise PostgresIndexError("Unable to update the PostgreSQL file index.") from None
        return len(current), changes

    def _read_catalog(self, connection: psycopg.Connection) -> dict[str, IndexedFile]:
        rows = connection.execute(
            """
            SELECT path, name, extension, size_bytes, modified_at, root
            FROM local_search.indexed_files
            WHERE catalog_id = %s
            """,
            (self.catalog_id,),
        )
        files = {}
        for row in rows:
            row["modified_at"] = row["modified_at"].astimezone(timezone.utc).isoformat()
            files[row["path"]] = IndexedFile(**row)
        return files

    def load(self) -> tuple[IndexedFile, ...]:
        """Read metadata for this catalog and enforce the local folder scope."""
        try:
            with psycopg.connect(self.dsn, connect_timeout=5, row_factory=dict_row) as connection:
                catalog = self._read_catalog(connection)
        except psycopg.Error as error:
            logger.error("PostgreSQL index read failed (%s).", type(error).__name__)
            raise PostgresIndexError("Unable to read the PostgreSQL file index.") from None

        authorized_roots = {str(root): root for root in self.roots}
        files = []
        for item in catalog.values():
            root = authorized_roots.get(item.root)
            path = Path(item.path)
            if root is None or not path.is_absolute() or ".." in path.parts or not is_within(path, root):
                continue
            files.append(item)
        return tuple(sorted(files, key=lambda item: (item.root.casefold(), item.path.casefold())))
