-- Artifact Hub MySQL 建表语句（MySQL 5.7+ / InnoDB / utf8mb4）。
--
-- 与 hub/src/artifact_hub/repositories/mysql.py 的 _ensure_schema 保持一致：
-- 服务启动时会自动执行同内容的 CREATE TABLE IF NOT EXISTS，修改本文件时需同步修改代码。
--
-- 约定：
--   * 普通索引 idx_<表名>_<字段>，唯一索引 uk_<表名>_<字段>；
--   * 业务 ID（UUID v4，定长 36）用 CHAR(36)，哈希（SHA-256 hex，定长 64）用 CHAR(64)；
--   * 时间为 ISO-8601 字符串（应用层解析），用 VARCHAR(64)；
--   * 枚举类字段用 VARCHAR + COMMENT 标注取值，不用 ENUM（避免扩展取值时改表）。

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
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Artifact 逻辑身份（同一来源文件的稳定归集）';

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
    UNIQUE KEY uk_dsh_artifact_versions_artifact_version (artifact_id, version),
    CONSTRAINT fk_dsh_version_artifact FOREIGN KEY (artifact_id) REFERENCES dsh_artifacts (artifact_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Artifact 不可变版本快照';

CREATE TABLE IF NOT EXISTS dsh_shares (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '内部自增行主键，不对外暴露',
    share_id CHAR(36) NOT NULL COMMENT '业务 ID（UUID v4）',
    artifact_version_id CHAR(36) NOT NULL COMMENT '指向的 Artifact Version',
    token_hash CHAR(64) NOT NULL COMMENT 'share token 的 SHA-256（hex），原始 token 不落库',
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
    INDEX idx_dsh_shares_created_by (created_by_id, created_at),
    CONSTRAINT fk_dsh_share_version FOREIGN KEY (artifact_version_id) REFERENCES dsh_artifact_versions (artifact_version_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '指向某个 Artifact Version 的访问分享';

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
    INDEX idx_dsh_uploads_artifact_state (artifact_id, state),
    CONSTRAINT fk_dsh_upload_artifact FOREIGN KEY (artifact_id) REFERENCES dsh_artifacts (artifact_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'NAS 两阶段上传的预留记录（prepare/commit）';
