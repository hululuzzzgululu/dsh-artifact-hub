"""MySQL adapter for the Artifact Hub repository interface."""

from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import text

from config.config_objects import ServerStorageConfig

from .base import ArtifactRepository, Record, Values


class MysqlArtifactRepository(ArtifactRepository):
    """Persist Artifact Hub metadata through a SQLAlchemy MySQL engine."""

    _LEGACY_TABLE_RENAMES = (
        ("artifacts", "dsh_artifacts"),
        ("artifact_versions", "dsh_artifact_versions"),
        ("shares", "dsh_shares"),
        ("uploads", "dsh_uploads"),
    )
    _BUSINESS_KEYS = (
        ("artifacts", "dsh_artifacts", "artifact_id"),
        ("artifact_versions", "dsh_artifact_versions", "artifact_version_id"),
        ("shares", "dsh_shares", "share_id"),
        ("uploads", "dsh_uploads", "upload_id"),
    )

    def __init__(self, engine: sa.Engine):
        self._engine = engine
        self._ensure_schema()

    @classmethod
    def from_config(cls, config: ServerStorageConfig):
        if config.url:
            url = config.url
        else:
            url = sa.URL.create(
                "mysql+pymysql",
                username=config.user,
                password=config.password,
                host=config.host,
                port=config.port,
                database=config.db,
                query={"charset": config.charset},
            )
        engine = sa.create_engine(
            url,
            pool_pre_ping=True,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
        )
        return cls(engine)

    def close(self) -> None:
        self._engine.dispose()

    def _ensure_schema(self) -> None:
        # Keep these statements in sync with hub/sqls/001_create_tables.sql
        # (enforced by test_mysql_schema_matches_the_sqls_file).
        statements = [
            """
            CREATE TABLE IF NOT EXISTS dsh_artifacts (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '内部自增行主键，不对外暴露',
                artifact_id CHAR(36) NOT NULL COMMENT '业务 ID（UUID v4），API 与外键使用',
                source_session_id VARCHAR(255) NOT NULL COMMENT '来源 DSH Session ID',
                source_path VARCHAR(512) NOT NULL COMMENT 'Session 工作区内的相对路径（禁止绝对路径与 ..）',
                name VARCHAR(255) NOT NULL COMMENT '展示文件名（单个安全文件名）',
                artifact_type VARCHAR(32) NULL COMMENT '按扩展名推断的类型：html|markdown|text|code|data|image|pdf|archive|other',
                dsh_workspace_id VARCHAR(128) NULL COMMENT '来源 DSH Workspace 的稳定 ID；未归入 Workspace 时为 NULL',
                dsh_workspace_path VARCHAR(512) NULL COMMENT '来源 DSH Workspace 的规范化绝对路径',
                dsh_workspace_title VARCHAR(255) NULL COMMENT '来源 DSH Workspace 的展示标题',
                created_by_id VARCHAR(128) NOT NULL COMMENT '创建者稳定 ID（可信调用方注入）',
                created_by_name VARCHAR(128) NOT NULL COMMENT '创建者展示名称；取不到时与 created_by_id 相同',
                created_at VARCHAR(64) NOT NULL COMMENT '创建时间（ISO-8601）',
                status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE' COMMENT '状态：ACTIVE（预留 INACTIVE）',
                UNIQUE KEY uk_dsh_artifacts_artifact_id (artifact_id),
                INDEX idx_dsh_artifacts_source (source_session_id, created_by_id, source_path(191))
            ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Artifact 逻辑身份（同一来源文件的稳定归集）'
            """,
            """
            CREATE TABLE IF NOT EXISTS dsh_artifact_versions (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '内部自增行主键，不对外暴露',
                artifact_version_id CHAR(36) NOT NULL COMMENT '业务 ID（UUID v4）',
                artifact_id CHAR(36) NOT NULL COMMENT '所属 Artifact',
                version INT UNSIGNED NOT NULL COMMENT '版本号，从 1 递增（含 NAS 预留号）',
                mime_type VARCHAR(255) NOT NULL COMMENT '按文件名推断的 MIME 类型',
                storage_mode VARCHAR(32) NOT NULL COMMENT '存储模式：LOCAL|NAS',
                storage_key VARCHAR(512) NOT NULL COMMENT 'artifact_root 下的相对存储路径，不存绝对路径',
                entrypoint VARCHAR(255) NULL COMMENT '多文件制品的入口文件名（预留，当前恒等于 name）',
                size_bytes BIGINT UNSIGNED NOT NULL COMMENT '内容字节数',
                checksum CHAR(64) NOT NULL COMMENT '内容 SHA-256（hex）',
                created_by_id VARCHAR(128) NOT NULL COMMENT '该版本发布者的稳定 ID',
                created_by_name VARCHAR(128) NOT NULL COMMENT '该版本发布者的展示名称；取不到时与 created_by_id 相同',
                created_at VARCHAR(64) NOT NULL COMMENT '创建时间（ISO-8601）',
                UNIQUE KEY uk_dsh_artifact_versions_artifact_version_id (artifact_version_id),
                UNIQUE KEY uk_dsh_artifact_versions_artifact_version (artifact_id, version)
            ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Artifact 不可变版本快照'
            """,
            """
            CREATE TABLE IF NOT EXISTS dsh_shares (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '内部自增行主键，不对外暴露',
                share_id CHAR(36) NOT NULL COMMENT '业务 ID（UUID v4）',
                artifact_version_id CHAR(36) NOT NULL COMMENT '指向的 Artifact Version',
                token_hash CHAR(64) NOT NULL COMMENT 'share token 的 SHA-256（hex），用于访问查找',
                token VARCHAR(64) NULL COMMENT 'share token 原文，同版本幂等重发时复用同一链接（历史数据为 NULL，重发后回填）',
                visibility VARCHAR(32) NOT NULL COMMENT '可见性：LINK（预留 PRIVATE）',
                permission VARCHAR(32) NOT NULL COMMENT '权限：VIEW_DOWNLOAD（预留 VIEW_ONLY）',
                expires_at VARCHAR(64) NULL COMMENT '过期时间（ISO-8601），NULL 表示永不过期',
                revoked_at VARCHAR(64) NULL COMMENT '撤销时间（ISO-8601），NULL 表示未撤销',
                created_by_id VARCHAR(128) NOT NULL COMMENT '分享创建者稳定 ID（可信调用方注入）',
                created_by_name VARCHAR(128) NOT NULL COMMENT '分享创建者展示名称；取不到时与 created_by_id 相同',
                created_at VARCHAR(64) NOT NULL COMMENT '创建时间（ISO-8601）',
                updated_at VARCHAR(64) NOT NULL COMMENT '最后更新时间（ISO-8601）',
                UNIQUE KEY uk_dsh_shares_share_id (share_id),
                UNIQUE KEY uk_dsh_shares_token_hash (token_hash),
                UNIQUE KEY uk_dsh_shares_artifact_version_id (artifact_version_id),
                INDEX idx_dsh_shares_created_by (created_by_id, created_at)
            ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '指向某个 Artifact Version 的访问分享'
            """,
            """
            CREATE TABLE IF NOT EXISTS dsh_uploads (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '内部自增行主键，不对外暴露',
                upload_id CHAR(36) NOT NULL COMMENT '业务 ID（UUID v4）',
                artifact_id CHAR(36) NOT NULL COMMENT '所属 Artifact',
                version INT UNSIGNED NOT NULL COMMENT '预留的版本号，从 1 递增',
                storage_mode VARCHAR(32) NOT NULL COMMENT '存储模式：恒为 NAS',
                storage_key VARCHAR(512) NOT NULL COMMENT 'artifact_root 下的相对存储路径，不存绝对路径',
                source_session_id VARCHAR(255) NOT NULL COMMENT '来源 DSH Session ID',
                source_path VARCHAR(512) NOT NULL COMMENT 'Session 工作区内的相对路径（禁止绝对路径与 ..）',
                name VARCHAR(255) NOT NULL COMMENT '展示文件名（单个安全文件名）',
                artifact_type VARCHAR(32) NULL COMMENT '按扩展名推断的类型：html|markdown|text|code|data|image|pdf|archive|other',
                created_by_id VARCHAR(128) NOT NULL COMMENT '上传预留创建者的稳定 ID（可信调用方注入）',
                created_by_name VARCHAR(128) NOT NULL COMMENT '上传预留创建者的展示名称；取不到时与 created_by_id 相同',
                created_at VARCHAR(64) NOT NULL COMMENT '创建时间（ISO-8601）',
                state VARCHAR(32) NOT NULL COMMENT '状态：PREPARED|COMMITTED',
                UNIQUE KEY uk_dsh_uploads_upload_id (upload_id),
                INDEX idx_dsh_uploads_artifact_state (artifact_id, state)
            ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'NAS 两阶段上传的预留记录（prepare/commit）'
            """,
        ]
        inspector = sa.inspect(self._engine)
        existing_tables = set(inspector.get_table_names())
        renames = []
        for legacy_name, current_name in self._LEGACY_TABLE_RENAMES:
            if legacy_name not in existing_tables:
                continue
            if current_name in existing_tables:
                raise RuntimeError(
                    "Cannot migrate legacy MySQL table {!r}: {!r} already exists".format(
                        legacy_name, current_name
                    )
                )
            renames.append("`{}` TO `{}`".format(legacy_name, current_name))

        old_identity_tables = []
        new_identity_tables = []
        columns_by_table = {}
        get_columns = getattr(inspector, "get_columns", None)
        if get_columns is not None:
            for legacy_name, current_name, business_key in self._BUSINESS_KEYS:
                source_name = (
                    current_name if current_name in existing_tables
                    else legacy_name if legacy_name in existing_tables
                    else None
                )
                if source_name is None:
                    continue
                columns = {column["name"] for column in get_columns(source_name)}
                columns_by_table[current_name] = columns
                if business_key in columns:
                    new_identity_tables.append(current_name)
                elif "id" in columns:
                    old_identity_tables.append(current_name)
        if old_identity_tables and new_identity_tables:
            raise RuntimeError(
                "Cannot migrate a mixed MySQL identity schema: old={!r}, new={!r}".format(
                    old_identity_tables, new_identity_tables
                )
            )

        share_source_table = (
            "dsh_shares" if "dsh_shares" in existing_tables
            else "shares" if "shares" in existing_tables
            else None
        )
        get_indexes = getattr(inspector, "get_indexes", None)
        indexes_by_table = {}
        if get_indexes is not None:
            for legacy_name, current_name, _business_key in self._BUSINESS_KEYS:
                source_name = (
                    current_name if current_name in existing_tables
                    else legacy_name if legacy_name in existing_tables
                    else None
                )
                if source_name is not None:
                    indexes_by_table[current_name] = get_indexes(source_name)
        share_has_version_uniqueness = False
        if share_source_table is not None and get_indexes is not None:
            share_has_version_uniqueness = any(
                index.get("unique")
                and index.get("column_names") == ["artifact_version_id"]
                for index in indexes_by_table.get("dsh_shares", [])
            )
        migrate_share_uniqueness = (
            share_source_table is not None and not share_has_version_uniqueness
        )

        with self._engine.begin() as connection:
            if renames:
                connection.execute(text("RENAME TABLE " + ", ".join(renames)))
            for statement in self._identity_migration_statements(old_identity_tables):
                connection.execute(text(statement))
            for statement in self._creator_workspace_migration_statements(
                columns_by_table, indexes_by_table
            ):
                connection.execute(text(statement))
            for statement in statements:
                connection.execute(text(statement))
            for statement in self._share_token_migration_statements(columns_by_table):
                connection.execute(text(statement))
            if migrate_share_uniqueness:
                for statement in self._share_uniqueness_migration_statements():
                    connection.execute(text(statement))

    @staticmethod
    def _share_token_migration_statements(columns_by_table):
        """Persist the raw share token so re-shares reuse the same link."""

        columns = columns_by_table.get("dsh_shares")
        if columns is None or "token" in columns:
            return []
        return [
            "ALTER TABLE dsh_shares ADD COLUMN token VARCHAR(64) NULL "
            "COMMENT 'share token 原文，同版本幂等重发时复用同一链接（历史数据为 NULL，重发后回填）'"
        ]

    @staticmethod
    def _creator_workspace_migration_statements(columns_by_table, indexes_by_table):
        """Backfill creator ID/name and add DSH workspace metadata in place."""

        statements = []
        old_creator_tables = {
            table_name
            for table_name, columns in columns_by_table.items()
            if "created_by" in columns
        }
        split_creator_tables = {
            table_name
            for table_name, columns in columns_by_table.items()
            if "created_by_id" in columns or "created_by_name" in columns
        }
        if old_creator_tables and split_creator_tables:
            raise RuntimeError(
                "Cannot migrate a mixed MySQL creator schema: old={!r}, new={!r}".format(
                    sorted(old_creator_tables), sorted(split_creator_tables)
                )
            )

        for table_name in (
            "dsh_artifacts", "dsh_artifact_versions", "dsh_shares", "dsh_uploads"
        ):
            columns = columns_by_table.get(table_name)
            if columns is None:
                continue
            additions = []
            if table_name == "dsh_artifacts":
                workspace_columns = (
                    ("dsh_workspace_id", "VARCHAR(128)", "来源 DSH Workspace 的稳定 ID；未归入 Workspace 时为 NULL"),
                    ("dsh_workspace_path", "VARCHAR(512)", "来源 DSH Workspace 的规范化绝对路径"),
                    ("dsh_workspace_title", "VARCHAR(255)", "来源 DSH Workspace 的展示标题"),
                )
                additions.extend(
                    "ADD COLUMN {} {} NULL COMMENT '{}'".format(name, sql_type, comment)
                    for name, sql_type, comment in workspace_columns
                    if name not in columns
                )
            if table_name in old_creator_tables:
                additions.extend((
                    "ADD COLUMN created_by_id VARCHAR(128) NULL COMMENT '创建者稳定 ID（可信调用方注入）'",
                    "ADD COLUMN created_by_name VARCHAR(128) NULL COMMENT '创建者展示名称；取不到时与 created_by_id 相同'",
                ))
            if additions:
                statements.append(
                    "ALTER TABLE {} {}".format(table_name, ", ".join(additions))
                )
            if table_name not in old_creator_tables:
                continue
            statements.append(
                "UPDATE {} SET created_by_id = LEFT(created_by, 128), "
                "created_by_name = LEFT(created_by, 128)".format(table_name)
            )

            alterations = [
                "MODIFY COLUMN created_by_id VARCHAR(128) NOT NULL",
                "MODIFY COLUMN created_by_name VARCHAR(128) NOT NULL",
            ]
            index_names = {
                index.get("name") for index in indexes_by_table.get(table_name, [])
            }
            if table_name == "dsh_artifacts":
                if "idx_dsh_artifacts_source" in index_names:
                    alterations.append("DROP INDEX idx_dsh_artifacts_source")
                alterations.extend((
                    "DROP COLUMN created_by",
                    "ADD INDEX idx_dsh_artifacts_source "
                    "(source_session_id, created_by_id, source_path(191))",
                ))
            elif table_name == "dsh_shares":
                if "idx_dsh_shares_created_by" in index_names:
                    alterations.append("DROP INDEX idx_dsh_shares_created_by")
                alterations.extend((
                    "DROP COLUMN created_by",
                    "ADD INDEX idx_dsh_shares_created_by (created_by_id, created_at)",
                ))
            else:
                alterations.append("DROP COLUMN created_by")
            statements.append(
                "ALTER TABLE {} {}".format(table_name, ", ".join(alterations))
            )
        return statements

    @staticmethod
    def _identity_migration_statements(old_tables):
        """Return ordered DDL for the original UUID-in-id MySQL layout."""

        old = set(old_tables)
        statements = []
        foreign_keys = (
            ("dsh_artifact_versions", "fk_dsh_version_artifact"),
            ("dsh_shares", "fk_dsh_share_version"),
            ("dsh_uploads", "fk_dsh_upload_artifact"),
        )
        for table_name, constraint_name in foreign_keys:
            if table_name in old:
                statements.append(
                    "ALTER TABLE {} DROP FOREIGN KEY {}".format(
                        table_name, constraint_name
                    )
                )

        alterations = {
            "dsh_artifacts": """
                ALTER TABLE dsh_artifacts
                    CHANGE COLUMN id artifact_id VARCHAR(36) NOT NULL,
                    DROP PRIMARY KEY,
                    ADD COLUMN id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST,
                    ADD UNIQUE KEY uk_dsh_artifacts_artifact_id (artifact_id)
            """,
            "dsh_artifact_versions": """
                ALTER TABLE dsh_artifact_versions
                    CHANGE COLUMN id artifact_version_id VARCHAR(36) NOT NULL,
                    MODIFY COLUMN artifact_id VARCHAR(36) NOT NULL,
                    DROP PRIMARY KEY,
                    ADD COLUMN id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST,
                    ADD UNIQUE KEY uk_dsh_artifact_versions_artifact_version_id (artifact_version_id)
            """,
            "dsh_shares": """
                ALTER TABLE dsh_shares
                    CHANGE COLUMN id share_id VARCHAR(36) NOT NULL,
                    MODIFY COLUMN artifact_version_id VARCHAR(36) NOT NULL,
                    DROP PRIMARY KEY,
                    ADD COLUMN id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST,
                    ADD UNIQUE KEY uk_dsh_shares_share_id (share_id)
            """,
            "dsh_uploads": """
                ALTER TABLE dsh_uploads
                    CHANGE COLUMN id upload_id VARCHAR(36) NOT NULL,
                    MODIFY COLUMN artifact_id VARCHAR(36) NOT NULL,
                    DROP PRIMARY KEY,
                    ADD COLUMN id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST,
                    ADD UNIQUE KEY uk_dsh_uploads_upload_id (upload_id)
            """,
        }
        for table_name, _business_key in (
            ("dsh_artifacts", "artifact_id"),
            ("dsh_artifact_versions", "artifact_version_id"),
            ("dsh_shares", "share_id"),
            ("dsh_uploads", "upload_id"),
        ):
            if table_name in old:
                statements.append(alterations[table_name])
        return statements

    @staticmethod
    def _share_uniqueness_migration_statements():
        """Deduplicate old rows before adding the per-version unique key."""

        return (
            """
            DELETE stale
            FROM dsh_shares AS stale
            INNER JOIN dsh_shares AS latest
                ON latest.artifact_version_id = stale.artifact_version_id
                AND latest.id > stale.id
            """,
            """
            ALTER TABLE dsh_shares
                ADD UNIQUE KEY uk_dsh_shares_artifact_version_id (artifact_version_id)
            """,
        )

    def create_artifact(self, values: Values) -> None:
        self._execute(
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
        with self._engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT artifact_id, source_session_id, source_path, "
                    "name, artifact_type, dsh_workspace_id, dsh_workspace_path, "
                    "dsh_workspace_title, created_by_id, created_by_name, "
                    "created_at, status "
                    "FROM dsh_artifacts WHERE artifact_id = :artifact_id"
                ),
                {"artifact_id": artifact_id},
            ).mappings().first()
        return dict(row) if row is not None else None

    def get_artifact_by_source(
        self, source_session_id: str, source_path: str, created_by_id: str
    ) -> Optional[Record]:
        with self._engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT artifact_id, source_session_id, source_path, "
                    "name, artifact_type, dsh_workspace_id, dsh_workspace_path, "
                    "dsh_workspace_title, created_by_id, created_by_name, "
                    "created_at, status "
                    "FROM dsh_artifacts "
                    "WHERE source_session_id = :source_session_id "
                    "AND source_path = :source_path "
                    "AND created_by_id = :created_by_id "
                    "ORDER BY id ASC LIMIT 1"
                ),
                {
                    "source_session_id": source_session_id,
                    "source_path": source_path,
                    "created_by_id": created_by_id,
                },
            ).mappings().first()
        return dict(row) if row is not None else None

    def next_version(self, artifact_id: str) -> int:
        with self._engine.connect() as connection:
            version = connection.execute(
                text(
                    "SELECT COALESCE(MAX(version), 0) + 1 AS next_version "
                    "FROM dsh_artifact_versions WHERE artifact_id = :artifact_id"
                ),
                {"artifact_id": artifact_id},
            ).scalar_one()
            pending = connection.execute(
                text(
                    "SELECT COALESCE(MAX(version), 0) + 1 AS next_version "
                    "FROM dsh_uploads WHERE artifact_id = :artifact_id "
                    "AND state = 'PREPARED'"
                ),
                {"artifact_id": artifact_id},
            ).scalar_one()
        return max(int(version), int(pending))

    def create_version(self, values: Values) -> None:
        self._execute(
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
        with self._engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT artifact_version_id, artifact_id, version, mime_type, "
                    "storage_mode, storage_key, entrypoint, size_bytes, checksum, "
                    "created_by_id, created_by_name, created_at "
                    "FROM dsh_artifact_versions "
                    "WHERE artifact_id = :artifact_id "
                    "ORDER BY version DESC LIMIT 1"
                ),
                {"artifact_id": artifact_id},
            ).mappings().first()
        return dict(row) if row is not None else None

    def upsert_share(self, values: Values) -> None:
        self._execute(
            """
            INSERT INTO dsh_shares
            (share_id, artifact_version_id, token_hash, token, visibility, permission,
             expires_at, revoked_at, created_by_id, created_by_name,
             created_at, updated_at)
            VALUES (:share_id, :artifact_version_id, :token_hash, :token, :visibility,
                    :permission, :expires_at, :revoked_at, :created_by_id,
                    :created_by_name, :created_at, :updated_at)
            ON DUPLICATE KEY UPDATE
                token_hash = VALUES(token_hash),
                token = VALUES(token),
                visibility = VALUES(visibility),
                permission = VALUES(permission),
                expires_at = VALUES(expires_at),
                revoked_at = VALUES(revoked_at),
                created_by_id = VALUES(created_by_id),
                created_by_name = VALUES(created_by_name),
                updated_at = VALUES(updated_at)
            """,
            values,
        )

    def create_upload(self, values: Values) -> None:
        self._execute(
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
        with self._engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT upload_id, artifact_id, version, storage_mode, storage_key, "
                    "source_session_id, source_path, name, artifact_type, "
                    "created_by_id, created_by_name, created_at, state "
                    "FROM dsh_uploads WHERE upload_id = :upload_id"
                ),
                {"upload_id": upload_id},
            ).mappings().first()
        return dict(row) if row is not None else None

    def mark_upload_committed(self, upload_id: str) -> bool:
        with self._engine.begin() as connection:
            result = connection.execute(
                text(
                    "UPDATE dsh_uploads SET state = 'COMMITTED' "
                    "WHERE upload_id = :upload_id AND state = 'PREPARED'"
                ),
                {"upload_id": upload_id},
            )
            return result.rowcount == 1

    def get_share_by_token_hash(self, token_hash: str) -> Optional[Record]:
        with self._engine.connect() as connection:
            row = connection.execute(
                text(self._share_query() + " WHERE s.token_hash = :token_hash"),
                {"token_hash": token_hash},
            ).mappings().first()
        return dict(row) if row is not None else None

    def get_share_by_id(self, share_id: str) -> Optional[Record]:
        with self._engine.connect() as connection:
            row = connection.execute(
                text(self._share_query() + " WHERE s.share_id = :share_id"),
                {"share_id": share_id},
            ).mappings().first()
        return dict(row) if row is not None else None

    def get_share_by_version_id(self, artifact_version_id: str) -> Optional[Record]:
        with self._engine.connect() as connection:
            row = connection.execute(
                text(
                    self._share_query()
                    + " WHERE s.artifact_version_id = :artifact_version_id"
                ),
                {"artifact_version_id": artifact_version_id},
            ).mappings().first()
        return dict(row) if row is not None else None

    def list_shares_by_creator(self, created_by_id: str) -> List[Record]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    self._share_query()
                    + " WHERE s.created_by_id = :created_by_id "
                    "ORDER BY s.created_at DESC"
                ),
                {"created_by_id": created_by_id},
            ).mappings().all()
        return [dict(row) for row in rows]

    def revoke_share(self, share_id: str, revoked_at: str) -> bool:
        with self._engine.begin() as connection:
            result = connection.execute(
                text(
                    "UPDATE dsh_shares SET revoked_at = :revoked_at, "
                    "updated_at = :updated_at "
                    "WHERE share_id = :share_id AND revoked_at IS NULL"
                ),
                {
                    "revoked_at": revoked_at,
                    "updated_at": revoked_at,
                    "share_id": share_id,
                },
            )
            return result.rowcount == 1

    def _execute(self, statement: str, values: Values) -> None:
        with self._engine.begin() as connection:
            connection.execute(text(statement), values)

    @staticmethod
    def _share_query() -> str:
        return """
            SELECT
                s.share_id AS share_id,
                s.artifact_version_id AS artifact_version_id,
                s.token_hash AS token_hash,
                s.token AS token,
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
                a.source_session_id AS source_session_id,
                a.source_path AS source_path,
                a.created_by_id AS artifact_created_by_id,
                a.created_by_name AS artifact_created_by_name
            FROM dsh_shares s
            JOIN dsh_artifact_versions av
                ON av.artifact_version_id = s.artifact_version_id
            JOIN dsh_artifacts a ON a.artifact_id = av.artifact_id
        """
