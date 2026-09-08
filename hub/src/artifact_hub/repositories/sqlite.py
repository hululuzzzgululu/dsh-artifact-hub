"""SQLite adapter for the Artifact Hub repository interface."""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

from .base import ArtifactRepository, Record, Values


class SqliteArtifactRepository(ArtifactRepository):
    """Persist Artifact Hub metadata in a local SQLite database."""

    _LEGACY_TABLE_RENAMES = (
        ("artifacts", "dsh_artifacts"),
        ("artifact_versions", "dsh_artifact_versions"),
        ("shares", "dsh_shares"),
        ("uploads", "dsh_uploads"),
    )
    _BUSINESS_KEYS = (
        ("dsh_artifacts", "artifact_id"),
        ("dsh_artifact_versions", "artifact_version_id"),
        ("dsh_shares", "share_id"),
        ("dsh_uploads", "upload_id"),
    )
    _CREATE_STATEMENTS = (
        """
        CREATE TABLE IF NOT EXISTS dsh_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artifact_id TEXT NOT NULL UNIQUE,
            source_session_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            name TEXT NOT NULL,
            artifact_type TEXT,
            dsh_workspace_id TEXT,
            dsh_workspace_path TEXT,
            dsh_workspace_title TEXT,
            created_by_id TEXT NOT NULL,
            created_by_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS dsh_artifact_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artifact_version_id TEXT NOT NULL UNIQUE,
            artifact_id TEXT NOT NULL REFERENCES dsh_artifacts(artifact_id),
            version INTEGER NOT NULL,
            mime_type TEXT NOT NULL,
            storage_mode TEXT NOT NULL,
            storage_key TEXT NOT NULL,
            entrypoint TEXT,
            size_bytes INTEGER NOT NULL,
            checksum TEXT NOT NULL,
            created_by_id TEXT NOT NULL,
            created_by_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(artifact_id, version)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS dsh_shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            share_id TEXT NOT NULL UNIQUE,
            artifact_version_id TEXT NOT NULL
                REFERENCES dsh_artifact_versions(artifact_version_id),
            token_hash TEXT NOT NULL UNIQUE,
            visibility TEXT NOT NULL,
            permission TEXT NOT NULL,
            expires_at TEXT,
            revoked_at TEXT,
            created_by_id TEXT NOT NULL,
            created_by_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS dsh_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id TEXT NOT NULL UNIQUE,
            artifact_id TEXT NOT NULL REFERENCES dsh_artifacts(artifact_id),
            version INTEGER NOT NULL,
            storage_mode TEXT NOT NULL,
            storage_key TEXT NOT NULL,
            source_session_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            name TEXT NOT NULL,
            artifact_type TEXT,
            created_by_id TEXT NOT NULL,
            created_by_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            state TEXT NOT NULL
        )
        """,
    )

    def __init__(self, database_path):
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.database_path, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def transaction(self):
        with self._lock:
            cursor = self._connection.cursor()
            try:
                yield cursor
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def _create_schema(self) -> None:
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = OFF")
            cursor = self._connection.cursor()
            try:
                cursor.execute("BEGIN")
                self._rename_legacy_tables(cursor)
                self._migrate_business_ids(cursor)
                self._migrate_creator_and_workspace_metadata(cursor)
                self._create_tables(cursor)
                self._migrate_share_uniqueness(cursor)
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()
                self._connection.execute("PRAGMA foreign_keys = ON")
            violations = self._connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError("SQLite schema migration left invalid foreign keys")

    def _create_tables(self, cursor) -> None:
        for statement in self._CREATE_STATEMENTS:
            cursor.execute(statement)

    def _migrate_creator_and_workspace_metadata(self, cursor) -> None:
        """Split legacy creator values and add Artifact workspace metadata."""

        existing_tables = {
            row[0]
            for row in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        present = [
            table_name
            for table_name, _business_key in self._BUSINESS_KEYS
            if table_name in existing_tables
        ]
        if not present:
            return

        columns_by_table = {
            table_name: {
                row[1]
                for row in cursor.execute(
                    'PRAGMA table_info("{}")'.format(table_name)
                ).fetchall()
            }
            for table_name in present
        }
        legacy = [
            table_name
            for table_name, columns in columns_by_table.items()
            if "created_by" in columns
        ]
        split = [
            table_name
            for table_name, columns in columns_by_table.items()
            if "created_by_id" in columns or "created_by_name" in columns
        ]
        if legacy and split:
            raise RuntimeError(
                "Cannot migrate a mixed SQLite creator schema: old={!r}, new={!r}".format(
                    legacy, split
                )
            )

        if legacy:
            legacy_names = {}
            for table_name in legacy:
                legacy_name = table_name + "__legacy_creator"
                cursor.execute(
                    'ALTER TABLE "{}" RENAME TO "{}"'.format(
                        table_name, legacy_name
                    )
                )
                legacy_names[table_name] = legacy_name

            self._create_tables(cursor)
            copies = {
                "dsh_artifacts": """
                    INSERT INTO dsh_artifacts
                    (artifact_id, source_session_id, source_path, name,
                     artifact_type, dsh_workspace_id, dsh_workspace_path,
                     dsh_workspace_title, created_by_id, created_by_name,
                     created_at, status)
                    SELECT artifact_id, source_session_id, source_path, name,
                           artifact_type, NULL, NULL, NULL, created_by, created_by,
                           created_at, status
                    FROM dsh_artifacts__legacy_creator
                """,
                "dsh_artifact_versions": """
                    INSERT INTO dsh_artifact_versions
                    (artifact_version_id, artifact_id, version, mime_type, storage_mode,
                     storage_key, entrypoint, size_bytes, checksum,
                     created_by_id, created_by_name, created_at)
                    SELECT artifact_version_id, artifact_id, version, mime_type,
                           storage_mode, storage_key, entrypoint, size_bytes, checksum,
                           created_by, created_by, created_at
                    FROM dsh_artifact_versions__legacy_creator
                """,
                "dsh_shares": """
                    INSERT INTO dsh_shares
                    (share_id, artifact_version_id, token_hash, visibility, permission,
                     expires_at, revoked_at, created_by_id, created_by_name,
                     created_at, updated_at)
                    SELECT share_id, artifact_version_id, token_hash, visibility,
                           permission, expires_at, revoked_at, created_by, created_by,
                           created_at, updated_at
                    FROM dsh_shares__legacy_creator
                """,
                "dsh_uploads": """
                    INSERT INTO dsh_uploads
                    (upload_id, artifact_id, version, storage_mode, storage_key,
                     source_session_id, source_path, name, artifact_type,
                     created_by_id, created_by_name, created_at, state)
                    SELECT upload_id, artifact_id, version, storage_mode, storage_key,
                           source_session_id, source_path, name, artifact_type,
                           created_by, created_by, created_at, state
                    FROM dsh_uploads__legacy_creator
                """,
            }
            for table_name in legacy:
                cursor.execute(copies[table_name])
            for table_name in (
                "dsh_shares", "dsh_uploads", "dsh_artifact_versions", "dsh_artifacts"
            ):
                legacy_name = legacy_names.get(table_name)
                if legacy_name is not None:
                    cursor.execute('DROP TABLE "{}"'.format(legacy_name))
            return

        artifact_columns = columns_by_table.get("dsh_artifacts", set())
        for column_name in (
            "dsh_workspace_id", "dsh_workspace_path", "dsh_workspace_title"
        ):
            if column_name not in artifact_columns:
                cursor.execute(
                    "ALTER TABLE dsh_artifacts ADD COLUMN {} TEXT".format(column_name)
                )

    @staticmethod
    def _migrate_share_uniqueness(cursor) -> None:
        """Keep the latest legacy row and enforce one Share per version."""

        cursor.execute(
            """
            DELETE FROM dsh_shares
            WHERE id NOT IN (
                SELECT latest_id
                FROM (
                    SELECT MAX(id) AS latest_id
                    FROM dsh_shares
                    GROUP BY artifact_version_id
                ) AS latest_shares
            )
            """
        )
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uk_dsh_shares_artifact_version_id
            ON dsh_shares (artifact_version_id)
            """
        )

    def _migrate_business_ids(self, cursor) -> None:
        """Move the original UUID-in-id layout to surrogate row IDs in place."""

        rows = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        existing_tables = {row[0] for row in rows}
        old_tables = []
        new_tables = []
        for table_name, business_key in self._BUSINESS_KEYS:
            if table_name not in existing_tables:
                continue
            columns = {
                row[1]
                for row in cursor.execute(
                    'PRAGMA table_info("{}")'.format(table_name)
                ).fetchall()
            }
            if business_key in columns:
                new_tables.append(table_name)
            elif "id" in columns:
                old_tables.append(table_name)
        if old_tables and new_tables:
            raise RuntimeError(
                "Cannot migrate a mixed SQLite identity schema: old={!r}, new={!r}".format(
                    old_tables, new_tables
                )
            )
        if not old_tables:
            return

        legacy_names = {}
        for table_name in old_tables:
            legacy_name = table_name + "__legacy_identity"
            cursor.execute(
                'ALTER TABLE "{}" RENAME TO "{}"'.format(table_name, legacy_name)
            )
            legacy_names[table_name] = legacy_name

        self._create_tables(cursor)
        copies = {
            "dsh_artifacts": """
                INSERT INTO dsh_artifacts
                (artifact_id, source_session_id, source_path, name,
                 artifact_type, dsh_workspace_id, dsh_workspace_path,
                 dsh_workspace_title, created_by_id, created_by_name,
                 created_at, status)
                SELECT id, source_session_id, source_path, name,
                       artifact_type, NULL, NULL, NULL, created_by, created_by,
                       created_at, status
                FROM dsh_artifacts__legacy_identity
            """,
            "dsh_artifact_versions": """
                INSERT INTO dsh_artifact_versions
                (artifact_version_id, artifact_id, version, mime_type, storage_mode,
                 storage_key, entrypoint, size_bytes, checksum,
                 created_by_id, created_by_name, created_at)
                SELECT id, artifact_id, version, mime_type, storage_mode,
                       storage_key, entrypoint, size_bytes, checksum,
                       created_by, created_by, created_at
                FROM dsh_artifact_versions__legacy_identity
            """,
            "dsh_shares": """
                INSERT INTO dsh_shares
                (share_id, artifact_version_id, token_hash, visibility, permission,
                 expires_at, revoked_at, created_by_id, created_by_name,
                 created_at, updated_at)
                SELECT id, artifact_version_id, token_hash, visibility, permission,
                       expires_at, revoked_at, created_by, created_by,
                       created_at, updated_at
                FROM dsh_shares__legacy_identity
            """,
            "dsh_uploads": """
                INSERT INTO dsh_uploads
                (upload_id, artifact_id, version, storage_mode, storage_key,
                 source_session_id, source_path, name, artifact_type,
                 created_by_id, created_by_name, created_at, state)
                SELECT id, artifact_id, version, storage_mode, storage_key,
                       source_session_id, source_path, name, artifact_type,
                       created_by, created_by, created_at, state
                FROM dsh_uploads__legacy_identity
            """,
        }
        for table_name in old_tables:
            cursor.execute(copies[table_name])
        for table_name in (
            "dsh_shares", "dsh_uploads", "dsh_artifact_versions", "dsh_artifacts"
        ):
            legacy_name = legacy_names.get(table_name)
            if legacy_name is not None:
                cursor.execute('DROP TABLE "{}"'.format(legacy_name))

    def _rename_legacy_tables(self, cursor) -> None:
        """Move the pre-prefix schema to the current table names in place."""

        rows = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        existing_tables = {row[0] for row in rows}
        for legacy_name, current_name in self._LEGACY_TABLE_RENAMES:
            if legacy_name not in existing_tables:
                continue
            if current_name in existing_tables:
                raise RuntimeError(
                    "Cannot migrate legacy SQLite table {!r}: {!r} already exists".format(
                        legacy_name, current_name
                    )
                )
            cursor.execute(
                'ALTER TABLE "{}" RENAME TO "{}"'.format(
                    legacy_name, current_name
                )
            )
            existing_tables.remove(legacy_name)
            existing_tables.add(current_name)

    def create_artifact(self, values: Values) -> None:
        with self.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO dsh_artifacts
                (artifact_id, source_session_id, source_path, name, artifact_type,
                 dsh_workspace_id, dsh_workspace_path, dsh_workspace_title,
                 created_by_id, created_by_name, created_at, status)
                VALUES (:artifact_id, :source_session_id, :source_path, :name,
                        :artifact_type, :dsh_workspace_id, :dsh_workspace_path,
                        :dsh_workspace_title, :created_by_id, :created_by_name,
                        :created_at, :status)
                """,
                values,
            )

    def get_artifact(self, artifact_id: str) -> Optional[Record]:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT artifact_id, source_session_id, source_path,
                       name, artifact_type, dsh_workspace_id, dsh_workspace_path,
                       dsh_workspace_title, created_by_id, created_by_name,
                       created_at, status
                FROM dsh_artifacts WHERE artifact_id = ?
                """,
                (artifact_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def get_artifact_by_source(
        self, source_session_id: str, source_path: str, created_by_id: str
    ) -> Optional[Record]:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT artifact_id, source_session_id, source_path,
                       name, artifact_type, dsh_workspace_id, dsh_workspace_path,
                       dsh_workspace_title, created_by_id, created_by_name,
                       created_at, status
                FROM dsh_artifacts
                WHERE source_session_id = ? AND source_path = ? AND created_by_id = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (source_session_id, source_path, created_by_id),
            ).fetchone()
        return self._row_to_dict(row)

    def next_version(self, artifact_id: str) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_version "
                "FROM dsh_artifact_versions WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            pending = self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_version "
                "FROM dsh_uploads WHERE artifact_id = ? AND state = 'PREPARED'",
                (artifact_id,),
            ).fetchone()
            return max(row["next_version"], pending["next_version"])

    def create_version(self, values: Values) -> None:
        with self.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO dsh_artifact_versions
                (artifact_version_id, artifact_id, version, mime_type, storage_mode, storage_key,
                 entrypoint, size_bytes, checksum, created_by_id, created_by_name, created_at)
                VALUES (:artifact_version_id, :artifact_id, :version, :mime_type, :storage_mode,
                        :storage_key, :entrypoint, :size_bytes, :checksum,
                        :created_by_id, :created_by_name, :created_at)
                """,
                values,
            )

    def get_latest_version(self, artifact_id: str) -> Optional[Record]:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT artifact_version_id, artifact_id, version, mime_type,
                       storage_mode, storage_key, entrypoint, size_bytes,
                       checksum, created_by_id, created_by_name, created_at
                FROM dsh_artifact_versions
                WHERE artifact_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (artifact_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def upsert_share(self, values: Values) -> None:
        with self.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO dsh_shares
                (share_id, artifact_version_id, token_hash, visibility, permission,
                 expires_at, revoked_at, created_by_id, created_by_name,
                 created_at, updated_at)
                VALUES (:share_id, :artifact_version_id, :token_hash, :visibility,
                        :permission, :expires_at, :revoked_at, :created_by_id,
                        :created_by_name, :created_at, :updated_at)
                ON CONFLICT(artifact_version_id) DO UPDATE SET
                    token_hash = excluded.token_hash,
                    visibility = excluded.visibility,
                    permission = excluded.permission,
                    expires_at = excluded.expires_at,
                    revoked_at = excluded.revoked_at,
                    created_by_id = excluded.created_by_id,
                    created_by_name = excluded.created_by_name,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                values,
            )

    def create_upload(self, values: Values) -> None:
        with self.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO dsh_uploads
                (upload_id, artifact_id, version, storage_mode, storage_key,
                 source_session_id, source_path, name, artifact_type,
                 created_by_id, created_by_name, created_at, state)
                VALUES (:upload_id, :artifact_id, :version, :storage_mode, :storage_key,
                        :source_session_id, :source_path, :name, :artifact_type,
                        :created_by_id, :created_by_name, :created_at, :state)
                """,
                values,
            )

    def get_upload(self, upload_id: str) -> Optional[Record]:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT upload_id, artifact_id, version, storage_mode, storage_key,
                       source_session_id, source_path, name, artifact_type,
                       created_by_id, created_by_name, created_at, state
                FROM dsh_uploads WHERE upload_id = ?
                """,
                (upload_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def mark_upload_committed(self, upload_id: str) -> bool:
        with self.transaction() as cursor:
            cursor.execute(
                "UPDATE dsh_uploads SET state = 'COMMITTED' "
                "WHERE upload_id = ? AND state = 'PREPARED'",
                (upload_id,),
            )
            return cursor.rowcount == 1

    def get_share_by_token_hash(self, token_hash: str) -> Optional[Record]:
        with self._lock:
            row = self._connection.execute(
                self._share_query() + " WHERE s.token_hash = ?", (token_hash,)
            ).fetchone()
        return self._row_to_dict(row)

    def get_share_by_id(self, share_id: str) -> Optional[Record]:
        with self._lock:
            row = self._connection.execute(
                self._share_query() + " WHERE s.share_id = ?", (share_id,)
            ).fetchone()
        return self._row_to_dict(row)

    def list_shares_by_creator(self, created_by_id: str) -> List[Record]:
        with self._lock:
            rows = self._connection.execute(
                self._share_query()
                + " WHERE s.created_by_id = ? ORDER BY s.created_at DESC",
                (created_by_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def revoke_share(self, share_id: str, revoked_at: str) -> bool:
        with self.transaction() as cursor:
            cursor.execute(
                "UPDATE dsh_shares SET revoked_at = ?, updated_at = ? "
                "WHERE share_id = ? AND revoked_at IS NULL",
                (revoked_at, revoked_at, share_id),
            )
            return cursor.rowcount == 1

    @staticmethod
    def _row_to_dict(row) -> Optional[Record]:
        return dict(row) if row is not None else None

    @staticmethod
    def _share_query() -> str:
        return """
            SELECT
                s.share_id AS share_id,
                s.artifact_version_id AS artifact_version_id,
                s.token_hash AS token_hash,
                s.visibility AS visibility,
                s.permission AS permission,
                s.expires_at AS expires_at,
                s.revoked_at AS revoked_at,
                s.created_by_id AS share_created_by_id,
                s.created_by_name AS share_created_by_name,
                s.created_at AS share_created_at,
                av.artifact_id AS artifact_id,
                av.version AS version,
                av.mime_type AS mime_type,
                av.storage_mode AS storage_mode,
                av.storage_key AS storage_key,
                av.size_bytes AS size_bytes,
                av.checksum AS checksum,
                a.name AS name,
                a.created_by_id AS artifact_created_by_id,
                a.created_by_name AS artifact_created_by_name
            FROM dsh_shares s
            JOIN dsh_artifact_versions av
                ON av.artifact_version_id = s.artifact_version_id
            JOIN dsh_artifacts a ON a.artifact_id = av.artifact_id
        """


# Preserve the old import name for callers that used the first MVP directly.
SQLiteRepository = SqliteArtifactRepository
