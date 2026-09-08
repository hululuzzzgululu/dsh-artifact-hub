import re
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from artifact_hub.repositories.mysql import MysqlArtifactRepository
from artifact_hub.repositories.sqlite import SqliteArtifactRepository


CURRENT_TABLES = {
    "dsh_artifacts",
    "dsh_artifact_versions",
    "dsh_shares",
    "dsh_uploads",
}
BUSINESS_KEYS = {
    "dsh_artifacts": "artifact_id",
    "dsh_artifact_versions": "artifact_version_id",
    "dsh_shares": "share_id",
    "dsh_uploads": "upload_id",
}
LEGACY_TABLES = {
    "artifacts",
    "artifact_versions",
    "shares",
    "uploads",
}


class _RecordingConnection:
    def __init__(self, statements):
        self._statements = statements

    def execute(self, statement, _values=None):
        self._statements.append(str(statement))


class _RecordingEngine:
    def __init__(self):
        self.statements = []

    @contextmanager
    def begin(self):
        yield _RecordingConnection(self.statements)

    def dispose(self):
        pass


class RepositorySchemaTests(unittest.TestCase):
    def test_sqlite_creates_only_dsh_prefixed_tables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hub.sqlite3"
            repository = SqliteArtifactRepository(database_path)
            repository.close()

            with sqlite3.connect(database_path) as connection:
                rows = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()

        table_names = {row[0] for row in rows}
        self.assertTrue(CURRENT_TABLES.issubset(table_names))
        self.assertTrue(LEGACY_TABLES.isdisjoint(table_names))

    def test_sqlite_uses_integer_row_ids_and_unique_business_ids(self):
        repository = SqliteArtifactRepository(":memory:")
        try:
            for table_name, business_key in BUSINESS_KEYS.items():
                columns = {
                    row["name"]: row
                    for row in repository._connection.execute(  # noqa: SLF001
                        'PRAGMA table_info("{}")'.format(table_name)
                    ).fetchall()
                }
                self.assertEqual(columns["id"]["type"], "INTEGER")
                self.assertEqual(columns["id"]["pk"], 1)
                self.assertEqual(columns[business_key]["type"], "TEXT")
                self.assertEqual(columns[business_key]["notnull"], 1)
                self.assertEqual(columns["created_by_id"]["type"], "TEXT")
                self.assertEqual(columns["created_by_id"]["notnull"], 1)
                self.assertEqual(columns["created_by_name"]["type"], "TEXT")
                self.assertEqual(columns["created_by_name"]["notnull"], 1)
                self.assertNotIn("created_by", columns)
                if table_name == "dsh_artifacts":
                    for workspace_column in (
                        "dsh_workspace_id",
                        "dsh_workspace_path",
                        "dsh_workspace_title",
                    ):
                        self.assertIn(workspace_column, columns)
                if table_name == "dsh_shares":
                    self.assertIn("token", columns)
                    self.assertEqual(columns["token"]["type"], "TEXT")
                    self.assertEqual(columns["token"]["notnull"], 0)
                indexes = repository._connection.execute(  # noqa: SLF001
                    'PRAGMA index_list("{}")'.format(table_name)
                ).fetchall()
                unique_columns = {
                    repository._connection.execute(  # noqa: SLF001
                        'PRAGMA index_info("{}")'.format(index["name"])
                    ).fetchone()["name"]
                    for index in indexes
                    if index["unique"] == 1
                }
                self.assertIn(business_key, unique_columns)
        finally:
            repository.close()

    def test_sqlite_renames_legacy_tables_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hub.sqlite3"
            with sqlite3.connect(database_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE artifacts (
                        id TEXT PRIMARY KEY,
                        source_session_id TEXT NOT NULL, source_path TEXT NOT NULL,
                        name TEXT NOT NULL, artifact_type TEXT, created_by TEXT NOT NULL,
                        created_at TEXT NOT NULL, status TEXT NOT NULL
                    );
                    INSERT INTO artifacts VALUES (
                        'art-1', 'session-1', 'report.md', 'report.md',
                        NULL, 'user-1', '2026-09-07T00:00:00Z', 'ACTIVE'
                    );
                    """
                )

            repository = SqliteArtifactRepository(database_path)
            artifact = repository.get_artifact("art-1")
            repository.close()

        self.assertEqual(artifact["artifact_id"], "art-1")
        self.assertEqual(artifact["name"], "report.md")
        self.assertEqual(artifact["created_by_id"], "user-1")
        self.assertEqual(artifact["created_by_name"], "user-1")
        self.assertNotIn("id", artifact)

    def test_sqlite_adds_the_token_column_to_an_existing_share_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hub.sqlite3"
            with sqlite3.connect(database_path) as connection:
                for statement in SqliteArtifactRepository._CREATE_STATEMENTS:  # noqa: SLF001
                    connection.execute(statement)
                # Recreate dsh_shares without the token column to model a
                # database written before the idempotent-token migration.
                connection.execute("DROP TABLE dsh_shares")
                connection.execute(
                    """
                    CREATE TABLE dsh_shares (
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
                    """
                )
                connection.execute(
                    """
                    INSERT INTO dsh_artifacts
                    (artifact_id, source_session_id, source_path, name, artifact_type,
                     dsh_workspace_id, dsh_workspace_path, dsh_workspace_title,
                     created_by_id, created_by_name, created_at, status)
                    VALUES ('art-1', 'session-1', 'report.md', 'report.md', NULL,
                            NULL, NULL, NULL, 'user-1', 'User One',
                            '2026-09-07T00:00:00Z', 'ACTIVE')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO dsh_artifact_versions
                    (artifact_version_id, artifact_id, version, mime_type, storage_mode,
                     storage_key, entrypoint, size_bytes, checksum,
                     created_by_id, created_by_name, created_at)
                    VALUES ('av-1', 'art-1', 1, 'text/markdown', 'LOCAL',
                            'artifacts/art-1/v1/report.md', 'report.md', 4, 'hash',
                            'user-1', 'User One', '2026-09-07T00:00:00Z')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO dsh_shares
                    (share_id, artifact_version_id, token_hash, visibility, permission,
                     expires_at, revoked_at, created_by_id, created_by_name,
                     created_at, updated_at)
                    VALUES ('share-1', 'av-1', 'token-hash-1', 'LINK', 'VIEW_DOWNLOAD',
                            NULL, NULL, 'user-1', 'User One',
                            '2026-09-07T00:00:00Z', '2026-09-07T00:00:00Z')
                    """
                )

            repository = SqliteArtifactRepository(database_path)
            share = repository.get_share_by_version_id("av-1")
            repository.close()

        self.assertEqual(share["share_id"], "share-1")
        self.assertIsNone(share["token"])
        self.assertEqual(share["source_session_id"], "session-1")
        self.assertEqual(share["source_path"], "report.md")

    def test_sqlite_get_share_by_version_id_returns_the_joined_row(self):
        repository = SqliteArtifactRepository(":memory:")
        try:
            repository.create_artifact(
                {
                    "artifact_id": "art-1",
                    "source_session_id": "session-1",
                    "source_path": "docs/report.md",
                    "name": "report.md",
                    "artifact_type": "markdown",
                    "dsh_workspace_id": None,
                    "dsh_workspace_path": None,
                    "dsh_workspace_title": None,
                    "created_by_id": "user-1",
                    "created_by_name": "User One",
                    "created_at": "2026-09-08T00:00:00Z",
                    "status": "ACTIVE",
                }
            )
            repository.create_version(
                {
                    "artifact_version_id": "av-1",
                    "artifact_id": "art-1",
                    "version": 1,
                    "mime_type": "text/markdown",
                    "storage_mode": "LOCAL",
                    "storage_key": "artifacts/art-1/v1/report.md",
                    "entrypoint": "report.md",
                    "size_bytes": 4,
                    "checksum": "hash",
                    "created_by_id": "user-1",
                    "created_by_name": "User One",
                    "created_at": "2026-09-08T00:00:00Z",
                }
            )
            repository.upsert_share(
                {
                    "share_id": "share-1",
                    "artifact_version_id": "av-1",
                    "token_hash": "token-hash-1",
                    "token": "token-raw-1",
                    "visibility": "LINK",
                    "permission": "VIEW_DOWNLOAD",
                    "expires_at": None,
                    "revoked_at": None,
                    "created_by_id": "user-1",
                    "created_by_name": "User One",
                    "created_at": "2026-09-08T00:00:00Z",
                    "updated_at": "2026-09-08T00:00:00Z",
                }
            )

            share = repository.get_share_by_version_id("av-1")

            self.assertEqual(share["share_id"], "share-1")
            self.assertEqual(share["token"], "token-raw-1")
            self.assertEqual(share["source_session_id"], "session-1")
            self.assertEqual(share["source_path"], "docs/report.md")
            self.assertIsNone(repository.get_share_by_version_id("av-missing"))
        finally:
            repository.close()

    def test_mysql_adds_the_token_column_when_missing(self):
        engine = _RecordingEngine()
        inspector = SimpleNamespace(
            get_table_names=lambda: ["dsh_shares"],
            get_columns=lambda _table_name: [
                {"name": "id"},
                {"name": "share_id"},
                {"name": "artifact_version_id"},
                {"name": "token_hash"},
                {"name": "visibility"},
                {"name": "permission"},
                {"name": "expires_at"},
                {"name": "revoked_at"},
                {"name": "created_by_id"},
                {"name": "created_by_name"},
                {"name": "created_at"},
                {"name": "updated_at"},
            ],
            get_indexes=lambda _table_name: [
                {
                    "name": "uk_dsh_shares_artifact_version_id",
                    "column_names": ["artifact_version_id"],
                    "unique": True,
                },
            ],
        )

        with patch(
            "artifact_hub.repositories.mysql.sa.inspect", return_value=inspector
        ):
            MysqlArtifactRepository(engine)

        migration = "\n".join(engine.statements)
        self.assertIn("ALTER TABLE dsh_shares ADD COLUMN token VARCHAR(64) NULL", migration)

    def test_sqlite_migrates_duplicate_version_shares_to_the_latest_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hub.sqlite3"
            with sqlite3.connect(database_path) as connection:
                for statement in SqliteArtifactRepository._CREATE_STATEMENTS:  # noqa: SLF001
                    connection.execute(statement)
                connection.execute(
                    """
                    INSERT INTO dsh_artifacts
                    (artifact_id, source_session_id, source_path, name, artifact_type,
                     dsh_workspace_id, dsh_workspace_path, dsh_workspace_title,
                     created_by_id, created_by_name, created_at, status)
                    VALUES ('art-1', 'session-1', 'report.md', 'report.md', NULL,
                            NULL, NULL, NULL, 'user-1', 'User One',
                            '2026-09-07T00:00:00Z', 'ACTIVE')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO dsh_artifact_versions
                    (artifact_version_id, artifact_id, version, mime_type, storage_mode,
                     storage_key, entrypoint, size_bytes, checksum,
                     created_by_id, created_by_name, created_at)
                    VALUES ('av-1', 'art-1', 1, 'text/markdown', 'LOCAL',
                            'artifacts/art-1/v1/report.md', 'report.md', 4, 'hash',
                            'user-1', 'User One', '2026-09-07T00:00:00Z')
                    """
                )
                for share_id, token_hash, created_at in (
                    ('share-1', 'token-hash-1', '2026-09-07T00:00:00Z'),
                    ('share-2', 'token-hash-2', '2026-09-07T01:00:00Z'),
                ):
                    connection.execute(
                        """
                        INSERT INTO dsh_shares
                        (share_id, artifact_version_id, token_hash, visibility,
                         permission, expires_at, revoked_at,
                         created_by_id, created_by_name,
                         created_at, updated_at)
                        VALUES (?, 'av-1', ?, 'LINK', 'VIEW_DOWNLOAD', NULL,
                                NULL, 'user-1', 'User One', ?, ?)
                        """,
                        (share_id, token_hash, created_at, created_at),
                    )

            repository = SqliteArtifactRepository(database_path)
            try:
                self.assertIsNone(repository.get_share_by_token_hash("token-hash-1"))
                self.assertEqual(
                    repository.get_share_by_token_hash("token-hash-2")["share_id"],
                    "share-2",
                )
                indexes = repository._connection.execute(  # noqa: SLF001
                    'PRAGMA index_list("dsh_shares")'
                ).fetchall()
                self.assertIn(
                    "uk_dsh_shares_artifact_version_id",
                    {index["name"] for index in indexes if index["unique"] == 1},
                )
            finally:
                repository.close()

    def test_sqlite_splits_legacy_creator_columns_in_the_current_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hub.sqlite3"
            with sqlite3.connect(database_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE dsh_artifacts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        artifact_id TEXT NOT NULL UNIQUE,
                        source_session_id TEXT NOT NULL, source_path TEXT NOT NULL,
                        name TEXT NOT NULL, artifact_type TEXT, created_by TEXT NOT NULL,
                        created_at TEXT NOT NULL, status TEXT NOT NULL
                    );
                    INSERT INTO dsh_artifacts
                    (artifact_id, source_session_id, source_path, name, artifact_type,
                     created_by, created_at, status)
                    VALUES ('art-current', 'session-1', 'report.md', 'report.md',
                            NULL, 'legacy-user', '2026-09-07T00:00:00Z', 'ACTIVE');
                    """
                )

            repository = SqliteArtifactRepository(database_path)
            try:
                artifact = repository.get_artifact("art-current")
                self.assertEqual(artifact["created_by_id"], "legacy-user")
                self.assertEqual(artifact["created_by_name"], "legacy-user")
                self.assertIsNone(artifact["dsh_workspace_id"])
                columns = {
                    row["name"]
                    for row in repository._connection.execute(  # noqa: SLF001
                        'PRAGMA table_info("dsh_artifacts")'
                    ).fetchall()
                }
                self.assertNotIn("created_by", columns)
            finally:
                repository.close()

    def test_sqlite_migrates_the_current_uuid_primary_key_schema_with_relations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "hub.sqlite3"
            with sqlite3.connect(database_path) as connection:
                connection.executescript(
                    """
                    PRAGMA foreign_keys = ON;
                    CREATE TABLE dsh_artifacts (
                        id TEXT PRIMARY KEY,
                        source_session_id TEXT NOT NULL, source_path TEXT NOT NULL,
                        name TEXT NOT NULL, artifact_type TEXT, created_by TEXT NOT NULL,
                        created_at TEXT NOT NULL, status TEXT NOT NULL
                    );
                    CREATE TABLE dsh_artifact_versions (
                        id TEXT PRIMARY KEY,
                        artifact_id TEXT NOT NULL REFERENCES dsh_artifacts(id),
                        version INTEGER NOT NULL, mime_type TEXT NOT NULL,
                        storage_mode TEXT NOT NULL, storage_key TEXT NOT NULL,
                        entrypoint TEXT, size_bytes INTEGER NOT NULL,
                        checksum TEXT NOT NULL, created_by TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(artifact_id, version)
                    );
                    CREATE TABLE dsh_shares (
                        id TEXT PRIMARY KEY,
                        artifact_version_id TEXT NOT NULL REFERENCES dsh_artifact_versions(id),
                        token_hash TEXT NOT NULL UNIQUE, visibility TEXT NOT NULL,
                        permission TEXT NOT NULL, expires_at TEXT, revoked_at TEXT,
                        created_by TEXT NOT NULL, created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE dsh_uploads (
                        id TEXT PRIMARY KEY,
                        artifact_id TEXT NOT NULL REFERENCES dsh_artifacts(id),
                        version INTEGER NOT NULL, storage_mode TEXT NOT NULL,
                        storage_key TEXT NOT NULL, source_session_id TEXT NOT NULL,
                        source_path TEXT NOT NULL, name TEXT NOT NULL,
                        artifact_type TEXT, created_by TEXT NOT NULL,
                        created_at TEXT NOT NULL, state TEXT NOT NULL
                    );
                    INSERT INTO dsh_artifacts VALUES (
                        'art-old', 'session-1', 'report.md', 'report.md',
                        NULL, 'user-1', '2026-09-07T00:00:00Z', 'ACTIVE'
                    );
                    INSERT INTO dsh_artifact_versions VALUES (
                        'av-old', 'art-old', 1, 'text/markdown', 'LOCAL',
                        'artifacts/art-old/v1/report.md', 'report.md', 4, 'hash',
                        'user-1', '2026-09-07T00:00:00Z'
                    );
                    INSERT INTO dsh_shares VALUES (
                        'share-old', 'av-old', 'token-hash', 'LINK', 'VIEW_DOWNLOAD',
                        NULL, NULL, 'user-1', '2026-09-07T00:00:00Z',
                        '2026-09-07T00:00:00Z'
                    );
                    INSERT INTO dsh_uploads VALUES (
                        'upload-old', 'art-old', 2, 'NAS',
                        'artifacts/art-old/v2/report.md', 'session-1', 'report.md',
                        'report.md', NULL, 'user-1',
                        '2026-09-07T00:00:00Z', 'PREPARED'
                    );
                    """
                )

            repository = SqliteArtifactRepository(database_path)
            try:
                self.assertEqual(repository.get_artifact("art-old")["artifact_id"], "art-old")
                self.assertEqual(repository.get_upload("upload-old")["upload_id"], "upload-old")
                share = repository.get_share_by_token_hash("token-hash")
                self.assertEqual(share["share_id"], "share-old")
                self.assertEqual(share["artifact_version_id"], "av-old")
                self.assertEqual(share["artifact_id"], "art-old")
                self.assertEqual(share["share_created_by_id"], "user-1")
                self.assertEqual(share["share_created_by_name"], "user-1")
                violations = repository._connection.execute(  # noqa: SLF001
                    "PRAGMA foreign_key_check"
                ).fetchall()
                self.assertEqual(violations, [])
            finally:
                repository.close()

    def test_mysql_schema_uses_dsh_prefixed_tables(self):
        engine = _RecordingEngine()
        inspector = SimpleNamespace(get_table_names=lambda: [])

        with patch(
            "artifact_hub.repositories.mysql.sa.inspect", return_value=inspector
        ):
            MysqlArtifactRepository(engine)

        created_tables = {
            match.group(1)
            for statement in engine.statements
            if (
                match := re.search(
                    r"CREATE TABLE IF NOT EXISTS ([a-z_]+)", statement
                )
            )
        }
        self.assertEqual(created_tables, CURRENT_TABLES)
        schema = "\n".join(engine.statements)
        for business_key in BUSINESS_KEYS.values():
            self.assertRegex(schema, rf"{business_key} CHAR\(36\) NOT NULL")
        self.assertEqual(schema.count("id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY"), 4)
        self.assertNotIn("uq_", schema)
        self.assertEqual(schema.count("created_by_id VARCHAR(128) NOT NULL"), 4)
        self.assertEqual(schema.count("created_by_name VARCHAR(128) NOT NULL"), 4)
        self.assertNotRegex(schema, r"\bcreated_by VARCHAR")
        for workspace_column in (
            "dsh_workspace_id VARCHAR(128)",
            "dsh_workspace_path VARCHAR(512)",
            "dsh_workspace_title VARCHAR(255)",
        ):
            self.assertIn(workspace_column, schema)
        for unique_index in (
            "uk_dsh_artifacts_artifact_id",
            "uk_dsh_artifact_versions_artifact_version_id",
            "uk_dsh_shares_share_id",
            "uk_dsh_shares_artifact_version_id",
            "uk_dsh_uploads_upload_id",
        ):
            self.assertIn(unique_index, schema)
        for plain_index in (
            "idx_dsh_artifacts_source",
            "idx_dsh_shares_created_by",
            "idx_dsh_uploads_artifact_state",
        ):
            self.assertIn(plain_index, schema)
        self.assertFalse(
            any(
                re.search(
                    r"CREATE TABLE IF NOT EXISTS "
                    r"(?:artifacts|artifact_versions|shares|uploads)\b",
                    statement,
                )
                for statement in engine.statements
            )
        )

    def test_mysql_schema_matches_the_sqls_file(self):
        sql_path = (
            Path(__file__).resolve().parent.parent / "sqls" / "001_create_tables.sql"
        )
        lines = [
            line
            for line in sql_path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("--")
        ]
        file_statements = [
            " ".join(statement.split())
            for statement in "\n".join(lines).split(";")
            if "CREATE TABLE" in statement
        ]

        engine = _RecordingEngine()
        inspector = SimpleNamespace(get_table_names=lambda: [])
        with patch(
            "artifact_hub.repositories.mysql.sa.inspect", return_value=inspector
        ):
            MysqlArtifactRepository(engine)
        code_statements = [
            " ".join(statement.split())
            for statement in engine.statements
            if "CREATE TABLE" in statement
        ]

        self.assertEqual(file_statements, code_statements)

    def test_mysql_renames_all_legacy_tables_together(self):
        engine = _RecordingEngine()
        inspector = SimpleNamespace(
            get_table_names=lambda: list(LEGACY_TABLES),
            get_columns=lambda _table_name: [{"name": "id"}],
        )

        with patch(
            "artifact_hub.repositories.mysql.sa.inspect", return_value=inspector
        ):
            MysqlArtifactRepository(engine)

        rename_statement = engine.statements[0]
        self.assertTrue(rename_statement.startswith("RENAME TABLE "))
        for legacy_name, current_name in MysqlArtifactRepository._LEGACY_TABLE_RENAMES:
            self.assertIn(
                "`{}` TO `{}`".format(legacy_name, current_name),
                rename_statement,
            )

        migration = "\n".join(engine.statements[1:])
        for table_name, business_key in BUSINESS_KEYS.items():
            self.assertRegex(
                migration,
                r"ALTER TABLE {}\s+CHANGE COLUMN id {} VARCHAR\(36\) NOT NULL".format(
                    table_name, business_key
                ),
            )
        self.assertEqual(
            migration.count(
                "ADD COLUMN id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST"
            ),
            4,
        )
        self.assertIn("DROP FOREIGN KEY fk_dsh_version_artifact", migration)
        self.assertIn("DROP FOREIGN KEY fk_dsh_share_version", migration)
        self.assertIn("DROP FOREIGN KEY fk_dsh_upload_artifact", migration)
        self.assertNotIn("ADD CONSTRAINT", migration)
        self.assertNotIn("REFERENCES", migration)
        self.assertIn(
            "ADD UNIQUE KEY uk_dsh_shares_artifact_version_id (artifact_version_id)",
            migration,
        )

    def test_mysql_migrates_existing_share_table_to_one_row_per_version(self):
        engine = _RecordingEngine()
        inspector = SimpleNamespace(
            get_table_names=lambda: ["dsh_shares"],
            get_columns=lambda _table_name: [
                {"name": "id"},
                {"name": "share_id"},
                {"name": "artifact_version_id"},
            ],
            get_indexes=lambda _table_name: [
                {
                    "name": "uk_dsh_shares_share_id",
                    "column_names": ["share_id"],
                    "unique": True,
                },
            ],
        )

        with patch(
            "artifact_hub.repositories.mysql.sa.inspect", return_value=inspector
        ):
            MysqlArtifactRepository(engine)

        migration = "\n".join(engine.statements)
        self.assertIn("DELETE stale", migration)
        self.assertIn("latest.id > stale.id", migration)
        self.assertIn(
            "ADD UNIQUE KEY uk_dsh_shares_artifact_version_id (artifact_version_id)",
            migration,
        )

    def test_mysql_splits_legacy_creator_columns_and_adds_workspace_metadata(self):
        engine = _RecordingEngine()
        columns = {
            "dsh_artifacts": ["id", "artifact_id", "created_by"],
            "dsh_artifact_versions": ["id", "artifact_version_id", "created_by"],
            "dsh_shares": ["id", "share_id", "artifact_version_id", "created_by"],
            "dsh_uploads": ["id", "upload_id", "created_by"],
        }
        indexes = {
            "dsh_artifacts": [{"name": "idx_dsh_artifacts_source"}],
            "dsh_shares": [{"name": "idx_dsh_shares_created_by"}],
        }
        inspector = SimpleNamespace(
            get_table_names=lambda: list(CURRENT_TABLES),
            get_columns=lambda table_name: [
                {"name": name} for name in columns[table_name]
            ],
            get_indexes=lambda table_name: indexes.get(table_name, []),
        )

        with patch(
            "artifact_hub.repositories.mysql.sa.inspect", return_value=inspector
        ):
            MysqlArtifactRepository(engine)

        migration = "\n".join(engine.statements)
        self.assertEqual(migration.count("LEFT(created_by, 128)"), 8)
        self.assertEqual(migration.count("DROP COLUMN created_by"), 4)
        self.assertIn("ADD COLUMN dsh_workspace_id VARCHAR(128)", migration)
        self.assertIn("ADD COLUMN dsh_workspace_path VARCHAR(512)", migration)
        self.assertIn("ADD COLUMN dsh_workspace_title VARCHAR(255)", migration)
        self.assertIn(
            "ADD INDEX idx_dsh_artifacts_source "
            "(source_session_id, created_by_id, source_path(191))",
            migration,
        )

    def test_mysql_share_upsert_preserves_share_id_and_created_at(self):
        engine = _RecordingEngine()
        inspector = SimpleNamespace(get_table_names=lambda: [])
        with patch(
            "artifact_hub.repositories.mysql.sa.inspect", return_value=inspector
        ):
            repository = MysqlArtifactRepository(engine)
        engine.statements.clear()

        repository.upsert_share(
            {
                "share_id": "share-new",
                "artifact_version_id": "av-1",
                "token_hash": "token-new",
                "token": "token-raw-new",
                "visibility": "LINK",
                "permission": "VIEW_DOWNLOAD",
                "expires_at": None,
                "revoked_at": None,
                "created_by_id": "user-1",
                "created_by_name": "User One",
                "created_at": "2026-09-08T00:00:00Z",
                "updated_at": "2026-09-08T00:00:00Z",
            }
        )

        statement = engine.statements[0]
        self.assertIn("ON DUPLICATE KEY UPDATE", statement)
        self.assertIn("token_hash = VALUES(token_hash)", statement)
        self.assertIn("token = VALUES(token)", statement)
        self.assertIn("expires_at = VALUES(expires_at)", statement)
        self.assertIn("revoked_at = VALUES(revoked_at)", statement)
        self.assertNotIn("share_id = VALUES(share_id)", statement)
        self.assertNotIn("created_at = VALUES(created_at)", statement)


if __name__ == "__main__":
    unittest.main()
