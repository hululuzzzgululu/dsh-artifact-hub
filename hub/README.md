# dsh-artifact-hub

一个轻量 Python Artifact Hub 后端，把 DSH Session File 固化成不可变 Artifact Version，并通过文件系统提供分享访问。

当前实现：

- `LOCAL`：Hub 直接读取 Session Workspace 并复制快照。
- `NAS`：Hub `prepare` 目标路径，调用方复制文件后再 `commit`。
- SQLite 保存 Artifact、Artifact Version、Share 和 NAS upload 状态。
- SQLite 和 MySQL 的物理表统一使用 `dsh_` 前缀：`dsh_artifacts`、`dsh_artifact_versions`、`dsh_shares`、`dsh_uploads`。每张表以自增 64 位 `id` 作为内部行主键，并以 UUID `artifact_id`、`artifact_version_id`、`share_id` 或 `upload_id` 作为对外业务键；启动时会迁移旧字符串主键结构并保留原有关联。
- Repository 通过抽象接口隔离数据库实现，当前提供 SQLite 和 MySQL adapters，可通过 `config.storage.mode` 切换。
- 配置模型参考 DataMind 的 `config_objects.py`：`HubConfig` 以顶层 `config` 对象包裹运行参数，`config.storage` 下包含 `mode`、`sqlite` 和 `server`，其中 `server` 表示 MySQL-compatible 数据库。
- API schema 和领域返回模型统一使用 Pydantic `BaseModel`，领域结果模型为不可变模型。
- 每个 Artifact Version 最多只有一条 Share；再次分享同一版本是幂等的：复用原 Share 的 `share_id`、token 和创建时间，仅更新有效期，旧链接保持有效。已撤销（revoked）的 Share 被重新分享时会换新 token 并清除撤销状态。
- 访问 token 同时保存原文与 SHA-256 hash：hash 用于访问查找，原文用于同版本幂等重发时返回同一链接（历史数据原文为 NULL，首次重发后回填）。可信创建者列表会为有效记录签发 10 分钟、进程级密钥签名的短时预览凭证。
- 暂不实现 ShareGrant、“分享给我的”、PRIVATE 分享、认证和对象存储。

## 本地一键联调

仓库根目录的 `scripts/dev.sh` 统一管理 Hub、share-web 和 DSH Web：

```bash
./scripts/dev.sh setup  # 首次安装依赖和本地 DSH 插件
./scripts/dev.sh test   # 三个子项目的测试、类型检查和构建
./scripts/dev.sh start  # 启动三个服务并自动执行 smoke test
```

也可以用 `./scripts/dev.sh all` 一次完成以上步骤。`start` 在前台托管三个进程，按 `Ctrl-C` 会停止本次启动的全部服务。默认端口分别是 Hub `8000`、share-web `5173`、DSH Web `3080`；复制 `scripts/dev.env.example` 为 `scripts/dev.env` 可覆盖配置。

## 启动

项目使用 `uv` 管理运行环境，HTTP 服务基于 FastAPI/Uvicorn，Python 3.9+ 可运行：

```bash
cd hub
uv run python -m api.main
```

也可以直接使用 Uvicorn：

```bash
cd hub
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
```

或使用启动脚本（可通过 `HUB_HOST`、`HUB_PORT` 等环境变量覆盖配置）：

```bash
./scripts/start.sh
```

默认目录：

```text
data/artifacts/  # Hub Artifact storage
data/hub.sqlite3 # Hub metadata
```

可通过环境变量覆盖：`HUB_HOST`、`HUB_PORT`、`HUB_BASE_URL`、`HUB_STORAGE_MODE`、`HUB_ARTIFACT_ROOT`、`HUB_DATABASE_PATH`。

Local 分享的 Session File 位于 DSH session 的 `header.cwd` workspace 中。DSH Host 根据浏览器提交的 `session_id` 查询可信 `workspace_root`，再从 `ctx.workspaceRegistry` 读取 Workspace 的稳定 ID、规范路径和标题，与相对 `source_path` 一起发送给 Hub；`session_id` 只作为来源元数据，不参与文件路径拼接。Hub 和 DSH Host 必须能以相同绝对路径访问该 workspace。

对应的 Pydantic 配置对象形状如下：

```json
{
  "config": {
    "storage": {
      "mode": "sqlite",
      "sqlite": { "path": "data/hub.sqlite3" },
      "server": {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "dsh_artifact_hub",
        "password": "",
        "db": "dsh_artifact_hub"
      }
    }
  }
}
```

数据库默认使用 SQLite。切换到 MySQL：

```bash
cd hub
HUB_STORAGE_MODE=mysql \\
HUB_MYSQL_URL='mysql+pymysql://user:password@127.0.0.1:3306/dsh_artifact_hub' \\
uv run python -m api.main
```

也可以使用 `HUB_MYSQL_HOST`、`HUB_MYSQL_PORT`、`HUB_MYSQL_USER`、`HUB_MYSQL_PASSWORD`、`HUB_MYSQL_DATABASE` 和连接池相关环境变量配置 MySQL。`HUB_STORAGE_MODE=server` 作为 DataMind 配置兼容别名。业务服务只依赖 repository interface，SQLite/MySQL 由 factory 创建。

服务启动时会自动把旧库中的 `created_by` 拆为 `created_by_id` 和 `created_by_name`，历史值同时回填两列；旧 Artifact 无法反推 Workspace 注册记录，因此新增的 `dsh_workspace_*` 列保持空值。新写入在创建者名称缺失时同样以 ID 回填名称。

## HTTP 接口

创建 Local 分享：

```http
POST /api/shares
Content-Type: application/json

{
  "session_id": "sess_001",
  "workspace_root": "/absolute/path/to/dsh/workspace",
  "source_path": "report.html",
  "dsh_workspace_id": "8cb72e5b-8d87-4d13-8919-ec65871f254c",
  "dsh_workspace_path": "/absolute/path/to/dsh/workspace",
  "dsh_workspace_title": "Research",
  "created_by_id": "user_a",
  "created_by_name": "Alice",
  "expires_at": "2026-12-31T16:00:00Z"
}
```

`workspace_root` 是管理 API 的可信调用参数，不应直接接受浏览器输入。仓库内的 DSH 插件会从 Host 的 live session store 获取它，并从 `ctx.workspaceRegistry` 取得 Workspace 的稳定 ID、规范路径和展示标题；未归入注册 Workspace 的旧 Session 仍会把 `header.cwd` 作为 `dsh_workspace_path`。Hub 会拒绝相对 workspace 路径以及逃出 workspace 的 `source_path`。`created_by_name` 可省略或留空，此时 Hub 会写入与 `created_by_id` 相同的值。

当前分享方式固定为“获得链接的任何人”（`LINK`），权限固定为“查看和下载”（`VIEW_DOWNLOAD`），创建接口无需传这两个字段，传入其他值会返回 422。`expires_at` 可选，接受 ISO-8601 时间；到期后元数据、预览和下载接口都会拒绝访问。

同一创建者再次分享同一 Session 的同一路径时，会复用原 Artifact；若文件 checksum 与最新版本一致，则复用 Artifact Version，并对该版本唯一的 Share 做幂等更新：保留 `share_id`、token 和创建时间，仅更新有效期，旧链接保持有效；若原 Share 已撤销，则重新生成 token 并清除撤销状态（旧链接仍然失效）。文件内容发生变化时才创建下一个 Artifact Version 及其 Share。

NAS 流程：

```http
POST /api/shares/prepare
{
  "session_id": "sess_001",
  "source_path": "report.html",
  "dsh_workspace_id": "8cb72e5b-8d87-4d13-8919-ec65871f254c",
  "dsh_workspace_path": "/absolute/path/to/dsh/workspace",
  "dsh_workspace_title": "Research",
  "created_by_id": "user_a",
  "created_by_name": "Alice"
}
```

把响应中的 `target_path` 复制到 NAS 后：

```http
POST /api/shares/commit
{
  "upload_id": "550e8400-e29b-41d4-a716-446655440001",
  "created_by_id": "user_a",
  "created_by_name": "Alice",
  "checksum": "<sha256>"
}
```

访问分享：

- `GET /s/{token}`：兼容用分享元数据接口（生产环境的同路径由 share-web 接管）。
- `GET /s/{token}/content`：兼容用原始内容接口。
- `GET /api/public/shares/{token}`：share-web 使用的最小公开元数据。
- `GET /api/public/shares/{token}/content`：用于在线预览的 inline 内容响应。
- `GET /api/public/shares/{token}/download`：下载内容。
- `GET /api/shares?created_by_id=user_a`：我创建的分享。
- `POST /api/shares/revoke`：撤销分享。

JSON 接口统一返回 `resultCode`、`resultMsg`、`resultObj` 三个字段；文件内容接口返回原始文件响应。公开元数据不会暴露 storage key、checksum 或内部 ID。公开内容响应使用 `no-store`、`nosniff` 等安全响应头；HTML 内容额外通过 CSP sandbox 限制执行环境。

生产环境的分享 URL `/s/{token}` 指向静态 `share-web`，它再访问 `/api/public/shares/*`。示例 Nginx 配置位于 `deploy/nginx/share-web.conf`。

## 测试

```bash
cd hub
uv run python -m unittest discover -s tests -v
```

编译检查：

```bash
cd hub
uv run python -m compileall -q src tests
```
