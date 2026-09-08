
# dsh-artifact-hub 概要设计

## 1. 背景

DeepSeek Harness 在 Agent 对话过程中会生成各种文件：

```
SQL / HTML / Markdown / PDF / Excel / CSV / 图片 / 其他文件
```

文件当前保存在 Session Workspace：

```
{session.header.cwd}/
├── query.sql
├── report.html
└── analysis.md
```

`session_id` 标识会话，但不是 workspace 目录名；同一个 workspace 也可以承载多个 Session。

当前用户如果希望把某个产物分享给其他人，一般只能：

```
分享整个 Session
       或
下载文件 → IM / 邮件再次发送
```

期望提供独立的 Artifact 分享能力：

```
Agent 生成文件
      ↓
Session Workspace
      ↓
用户点击 [分享]
      ↓
固化 Artifact Version
      ↓
生成分享链接
      ↓
其他用户在线查看 / 下载
```

同时增加统一的：

```
分享中心
├── 我分享的
└── 分享给我的
```

---

# 2. 本期范围

本期只支持两种 Artifact Storage 模式：

```
LOCAL
NAS
```

暂不考虑：

```
S3
OSS
COS
MinIO Object API
其他对象存储
```

其中 NAS 对应用进程而言仍然是文件系统。

---

# 3. 核心设计原则

## 3.1 Session File 不等于 Artifact

Agent 正常生成：

```
{session.header.cwd}/report.html
```

此时只是：

```
Session File
```

特点：

```
mutable
生命周期跟 Session 相关
可能被 Agent 修改
可能被 Session 清理
```

此时：

```
不创建 Artifact
不创建 ArtifactVersion
不复制文件
不产生 Share
```

只有用户点击：

```
[分享]
```

才进入 Artifact 生命周期。

---

## 3.2 Artifact 是逻辑产物

Artifact 表示：

> 某个 Session 文件形成的稳定业务身份。

例如：

```
Artifact
550e8400-e29b-41d4-a716-446655440000

name        = report.html
session_id  = sess_123
source_path = report.html
```

Artifact 本身不保存具体文件内容。

---

## 3.3 ArtifactVersion 是不可变快照

第一次分享：

```
Session File
      ↓
Artifact
      ↓
ArtifactVersion v1
```

Session 文件后续继续修改：

```
Artifact
├── v1
├── v2
└── v3
```

每个 ArtifactVersion：

```
immutable
```

已经分享出去的内容不会发生变化。

---

## 3.4 Share 指向 ArtifactVersion

核心关系：

```
Artifact
   │
   ▼
ArtifactVersion
   │
   ▼
 Share
```

每个 ArtifactVersion 最多对应一个当前 Share。再次分享同一版本会覆盖该 Share 的链接和配置，而不是新增一条点击历史。

而不是：

```
Share → Session File
```

这样 Share 生命周期与原 Session 解耦。

---

# 4. 核心领域模型

```
Session File
     │
     │ first share
     ▼
 Artifact
     │
     │ snapshot
     ▼
ArtifactVersion
     │
     │ authorization
     ▼
   Share
     │
     │ recipient
     ▼
 ShareGrant
```

---

## 4.1 Artifact

```
Artifact
-------------------------
id

source_session_id
source_path

name
artifact_type

dsh_workspace_id
dsh_workspace_path
dsh_workspace_title

created_by_id
created_by_name
created_at
status
```

Artifact 表示逻辑身份。

---

## 4.2 ArtifactVersion

```
ArtifactVersion
-------------------------
id
artifact_id
version

mime_type

storage_mode
storage_key
entrypoint

size
checksum

created_by_id
created_by_name
created_at
```

其中：

```
storage_mode = LOCAL | NAS
```

`storage_key` 使用相对路径，不保存实际机器绝对路径。

例如：

```
artifacts/550e8400-e29b-41d4-a716-446655440000/v1/
```

---

## 4.3 Share

```
Share
-------------------------
id
artifact_version_id

token_hash

UNIQUE(artifact_version_id)

visibility
permission

expires_at
revoked_at

created_by_id
created_by_name
created_at
updated_at
```

---

## 4.4 ShareGrant

```
ShareGrant
-------------------------
id
share_id

subject_type
subject_id

created_at
```

例如：

```
USER
GROUP
```

主要用于：

```
分享给我的
```

查询。

---

# 5. 分享模式

本期只支持链接分享：获得链接的任何人都可访问，并可查看和下载。

```
Share
visibility = LINK
permission = VIEW_DOWNLOAD
```

`visibility` 和 `permission` 不是用户可选项。组织内分享、指定用户分享与 ShareGrant 不在本期范围内。

---

# 6. 产品形态

整体分成三个入口：

```
                Artifact Sharing
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼

     创建分享        分享中心        分享页面
```

---

# 7. DSH 文件分享入口

对话中：

```
report.html

[预览] [下载] [分享]
```

点击分享：

```
分享 report.html

分享方式
获得链接的任何人

权限
查看和下载

有效期
[截止时间（可选）]

                  [创建分享]
```

---

# 8. 分享中心

建议作为 DSH 左侧一级入口：

```
DeepSeek Harness

+ New Session

Sessions
...

────────────
分享
────────────

Settings
```

进入：

```
分享中心

[我分享的]   [分享给我的]
```

---

## 8.1 我分享的

以 Artifact 为主视角展示：

```
销售分析报告
HTML

最新版本：v3
已分享版本：3
最近分享：09-07

[预览] [再次分享] [分享记录]
```

展开：

```
Artifact

├── v1
│   └── Share A
│
├── v2
│   ├── Share B
│   └── Share C
│
└── v3
    └── Share D
```

---

## 8.2 分享给我的

根据：

```
ShareGrant.subject_id = current_user
```

查询。

展示：

```
Artifact Name
Type
Shared By
Shared At
Expires At
Permission
```

操作：

```
预览
下载
```

---

# 9. Share 页面

分享链接：

```
https://share.xxx.com/s/{token}
```

访问：

```
Share
  ↓
ArtifactVersion
  ↓
Viewer
```

页面：

```
┌──────────────────────────────────┐
│ 销售分析报告                      │
│ HTML · Alice 分享                 │
│                                  │
│        Artifact Preview          │
│                                  │
│                     [下载]       │
└──────────────────────────────────┘
```

Share 页面与：

```
原 Session
原 DSH Pod
```

均解耦。

---

# 10. Artifact Storage

本期统一定义：

```
ArtifactStorage
     │
     ├── LOCAL
     └── NAS
```

两者本质上都是文件系统存储。

区别主要是：

```
LOCAL
Artifact Hub 所在机器本地磁盘

NAS
DSH 与 Artifact Hub 均可访问的共享文件系统
```

---

# 11. Local 模式

## 11.1 部署要求

Local 模式推荐：

> DSH 与 Artifact Hub 在同一台机器，或者至少 Artifact Hub 能直接访问 DSH Session Workspace。

典型：

```
Machine
│
├── DSH
│    └── /data/sessions/
│
└── Artifact Hub
     ├── /data/sessions/     RO
     └── /data/artifacts/    RW
```

---

## 11.2 数据流

用户点击分享：

```
DSH Plugin
    │
    │ session_id + source_path
    ▼
Artifact Hub
    │
    │ read Session File
    │ checksum
    │ copy
    ▼
Local Artifact Storage
```

具体：

```
/data/sessions/sess_001/report.html

             │
             │ Hub snapshot
             ▼

/data/artifacts/550e8400-e29b-41d4-a716-446655440000/v1/report.html
```

---

## 11.3 Local 模式职责

```
DSH Plugin
──────────
告诉 Hub：
session_id
source_path
分享配置


Artifact Hub
────────────
读取 Session File
计算 checksum
创建 Artifact
创建 ArtifactVersion
执行 copy
写数据库
创建 Share
```

Local 模式下：

> 文件 copy 由 Artifact Hub 完成。

---

# 12. NAS 模式

NAS 模式主要面向：

```
DSH Session File 在本地磁盘
+
DSH 同时可以访问 NAS
+
Artifact Hub 也可以访问 NAS
```

例如：

```
DSH Machine
├── /data/sessions/
└── /mnt/nas/artifacts/

Hub Machine
└── /mnt/nas/artifacts/
```

这种情况下 Hub 无法直接访问：

```
DSH 本地 Session File
```

但 DSH 可以直接写 NAS。

因此无需：

```
DSH → HTTP Upload → Hub → NAS
```

---

# 13. NAS 模式数据流

推荐：

```
DSH Session File
      │
      │ DSH Plugin copy
      ▼
NAS Temporary / Target Path
      │
      │ register
      ▼
Artifact Hub
      │
      ├── validate
      ├── checksum
      ├── create Artifact
      ├── create ArtifactVersion
      ├── create Share
      └── write DB
```

整体：

```
DSH
 │
 │ local session file
 ▼
DSH Plugin
 │
 │ filesystem copy
 ▼
NAS
 │
 │ storage reference
 ▼
Artifact Hub
 │
 ▼
Database
```

---

# 14. 为什么 NAS 模式由 DSH copy

如果 Session File 是：

```
DSH 本地磁盘
```

Hub 在另一台机器：

```
无法读取
```

但 DSH 又已经挂载：

```
/mnt/nas/artifacts
```

那么最简单的数据路径就是：

```
DSH Local Disk
      ↓
 filesystem copy
      ↓
NAS
```

避免：

```
DSH
 ↓ HTTP
Hub
 ↓ filesystem
NAS
```

减少一次数据中转。

---

# 15. NAS 模式下的职责边界

虽然文件由 DSH copy，但 Artifact 的业务控制权仍然在 Hub。

建议采用两阶段流程：

```
① prepare
② copy
③ commit
```

---

## 15.1 Prepare

DSH Plugin 请求：

```
POST /api/shares/prepare
```

Hub：

```
创建 artifact_id
计算 version number
分配 storage_key
返回目标路径信息
```

例如：

```
{
  "artifact_id": "550e8400-e29b-41d4-a716-446655440000",
  "version": 1,
  "upload_id": "550e8400-e29b-41d4-a716-446655440001",
  "storage_key": "artifacts/550e8400-e29b-41d4-a716-446655440000/v1/"
}
```

---

## 15.2 Copy

DSH：

```
source:

/data/sessions/sess_001/report.html
```

copy：

```
/mnt/nas/artifacts/550e8400-e29b-41d4-a716-446655440000/v1/report.html
```

---

## 15.3 Commit

DSH Plugin：

```
POST /api/shares/commit
```

Hub：

```
确认文件存在
读取 metadata
计算 / 校验 checksum
创建 ArtifactVersion
创建 Share
创建 ShareGrant
完成事务
```

最终返回：

```
https://share.xxx.com/s/xxxx
```

---

# 16. Local 与 NAS 模式对比

||Local|NAS|
|---|---|---|
|Session File|Hub 可访问|通常仅 DSH 本地可访问|
|Artifact Storage|Hub 本地磁盘|NAS|
|谁执行 copy|Hub|DSH Plugin|
|是否 HTTP 上传文件|否|否|
|Hub 是否管理 Artifact ID|是|是|
|Hub 是否分配 storage path|是|是|
|Hub 是否写 Artifact DB|是|是|
|Share 创建|Hub|Hub|

最重要的原则：

```
谁负责搬 bytes 可以不同

但：

Artifact identity
Version
Storage key
Metadata
Share
访问规则
生命周期

始终由 Hub 管理
```

---

# 17. Storage Path

建议物理目录：

```
artifacts/
└── {artifact_id}/
    └── v{version}/
        └── content
```

例如：

```
artifacts/
└── 550e8400-e29b-41d4-a716-446655440000/
    ├── v1/
    │   └── report.html
    └── v2/
        └── report.html
```

数据库保存：

```
storage_key =
550e8400-e29b-41d4-a716-446655440000/v1/
```

不要保存：

```
/mnt/nas/...
/data/...
```

绝对路径由配置决定。

---

# 18. 配置设计

Artifact Hub 配置示例。

Local：

```
storage:
  mode: local
  artifact_root: /data/artifacts
```

Local 模式的源文件根目录不是 Hub 的静态配置。DSH Host 根据 `session_id` 从 live session store 取得可信的 `header.cwd`，并在管理请求中作为 `workspace_root` 传给 Hub；同时从 `ctx.workspaceRegistry` 的 Session 成员关系读取 Workspace `id/path/title`，写入 Artifact 的 `dsh_workspace_*` 元数据。未归入注册 Workspace 的 Session 仍以 `header.cwd` 回填路径，ID 和标题为空。浏览器不能提供这些字段。

NAS：

```
storage:
  mode: nas
  artifact_root: /mnt/nas/artifacts
```

DSH Plugin NAS 配置：

```
artifact_hub:
  mode: nas
  service_url: http://artifact-hub:8080
  artifact_root: /mnt/nas/artifacts
```

Hub 与 DSH 的：

```
artifact_root
```

可以是不同 mount path。

因此更推荐 Hub 返回：

```
storage_key
```

DSH 根据自己的配置：

```
artifact_root + storage_key
```

得到实际 NAS 路径。

---

# 19. 数据库模型

当前实现四张 `dsh_` 表。每张表的 `id` 是数据库内部自增 64 位行主键；命名业务 ID 是唯一 UUID，并用于外键及 API。

## artifact

```
artifact
--------------------------
id
artifact_id

source_session_id
source_path

name
artifact_type

dsh_workspace_id
dsh_workspace_path
dsh_workspace_title

created_by_id
created_by_name
created_at
status
```

---

## artifact_version

```
artifact_version
--------------------------
id
artifact_version_id
artifact_id
version

mime_type

storage_mode
storage_key
entrypoint

size
checksum

created_by_id
created_by_name
created_at
```

---

## artifact_share

```
artifact_share
--------------------------
id
share_id
artifact_version_id

token_hash

UNIQUE(artifact_version_id)

visibility
permission

expires_at
revoked_at

created_by_id
created_by_name
created_at
updated_at
```

---

## artifact_upload

```
artifact_upload
--------------------------
id
upload_id
artifact_id
version

storage_mode
storage_key

source_session_id
source_path
name
artifact_type
created_by_id
created_by_name
created_at
state
```

`artifact_share_grant` 是后续能力，当前尚未建表。

关系：

```
Artifact
   1
   │
   N
ArtifactVersion
   1
   │
  0..1
Share

Artifact
   1
   │
   N
ArtifactUpload
```

---

# 20. Artifact 版本判断

分享前计算当前文件：

```
checksum
```

如果 Artifact 已存在，且最新 Version：

```
checksum == current checksum
```

则：

```
复用 ArtifactVersion
创建或覆盖该 ArtifactVersion 唯一的 Share
```

否则：

```
创建新的 ArtifactVersion
```

例如：

```
Artifact 550e8400-e29b-41d4-a716-446655440000

v1 checksum AAA

Session File checksum AAA
→ 复用 v1

Session File checksum BBB
→ 创建 v2
```

---

# 21. API 草案

主要分成普通管理 API 与 NAS 两阶段 API。

## Local 创建分享

```
POST /api/shares
```

例如：

```
{
  "session_id": "sess_123",
  "source_path": "report.html",
  "expires_at": "2026-12-31T16:00:00Z"
}
```

Hub 自己执行 snapshot。分享方式固定为 `LINK`，权限固定为 `VIEW_DOWNLOAD`；`expires_at` 可选。

---

## NAS Prepare

```
POST /api/shares/prepare
```

返回：

```
{
  "artifact_id": "550e8400-e29b-41d4-a716-446655440000",
  "version": 1,
  "upload_id": "550e8400-e29b-41d4-a716-446655440001",
  "storage_key": "550e8400-e29b-41d4-a716-446655440000/v1/"
}
```

---

## NAS Commit

```
POST /api/shares/commit
```

Request：

```
{
  "upload_id": "550e8400-e29b-41d4-a716-446655440001",
  "entrypoint": "report.html",
  "expires_at": "2026-12-31T16:00:00Z"
}
```

---

其他：

```
GET    /api/shares/mine
GET    /api/shares/shared-with-me
GET    /api/shares/{share_id}

PATCH  /api/shares/{share_id}
DELETE /api/shares/{share_id}

GET    /s/{token}
GET    /s/{token}/download
```

---

# 22. Sharing Service

Hub 独立部署，主要负责：

```
Artifact
ArtifactVersion

Share

Storage path allocation

Local Snapshot

NAS Prepare / Commit

Checksum validation

固定链接访问规则
有效期
撤销

我分享的

Preview / Download metadata

生命周期管理
```

---

# 23. DSH Plugin

负责：

```
文件后的 [分享]

Share Dialog

获取：
session_id
source_path

Local:
调用 Hub，由 Hub copy

NAS:
调用 prepare
执行 Session → NAS copy
调用 commit

分享中心

我分享的
```

DSH Plugin 不负责：

```
Artifact 数据库
Share 数据库
版本管理
分享 Token
```

---

# 24. Share Web

独立 Share Web：

```
/s/{token}
```

负责：

```
过期提示
撤销提示

Artifact Preview
Download
```

Viewer：

```
SQL        → Code
Markdown   → Markdown
JSON       → JSON
PDF        → PDF
Image      → Image
HTML       → Sandbox
其他        → Download
```

---

# 25. HTML 安全

Agent HTML 视为不可信内容。

推荐：

```
app.xxx.com       DSH
share.xxx.com     Share Web
artifact.xxx.com  HTML Content
```

HTML 使用：

```
iframe sandbox
CSP
Origin 隔离
Cookie 隔离
```

避免访问 DSH 登录态和主站 API。

---

# 26. 系统架构

```
                         User
                          │
                 ┌────────┴────────┐
                 ▼                 ▼

               DSH            Share Web
                │                 │
                │                 │
                └───────┬─────────┘
                        ▼
                 Artifact Hub
                        │
             ┌──────────┴───────────┐
             ▼                      ▼

          Database           Artifact Storage
                                  │
                           ┌──────┴──────┐
                           ▼             ▼
                         Local           NAS
```

数据路径则根据模式变化。

---

# 27. Local 数据路径

```
             same/shared filesystem

DSH Session File
       │
       │ reference
       ▼
 Artifact Hub
       │
       │ copy
       ▼
Local Artifact Storage
       │
       ▼
ArtifactVersion
       │
       ▼
      Share
```

---

# 28. NAS 数据路径

```
DSH Local Session File
       │
       │ filesystem copy
       ▼
      NAS
       │
       │ commit storage_ref
       ▼
 Artifact Hub
       │
       ├── ArtifactVersion
       ├── Share
       └── ShareGrant
```

特点：

```
文件不经过 Hub HTTP
```

---

# 29. 工程结构

采用 Monorepo：

```
dsh-artifact-hub/
│
├── hub/
│   ├── src/
│   │   ├── api/
│   │   │   ├── main.py
│   │   │   ├── response.py
│   │   │   └── routers/
│   │   │
│   │   ├── config/
│   │   │   └── manager.py
│   │   │
│   │   └── artifact_hub/
│   │       ├── domain/
│   │       ├── services/
│   │       ├── storage/
│   │       ├── repositories/
│   │       ├── auth/
│   │       └── common/
│   │
│   ├── tests/
│   ├── pyproject.toml
│   └── README.md
│
├── plugins/
│   └── dsh-artifact-hub/
│       └── src/
│           ├── host/
│           └── client/
│
├── apps/
│   └── share-web/
│       └── src/
│
├── contracts/
│   └── openapi.yaml
│
├── docs/
├── deploy/
├── README.md
└── LICENSE
```

---

# 30. Hub 工程结构

```
hub/src/
├── api/
│   ├── main.py
│   ├── response.py
│   └── routers/
│
├── config/
│   └── manager.py
│
└── artifact_hub/
    ├── domain/
    ├── services/
    ├── storage/
    ├── repositories/
    ├── auth/
    └── common/
```

---

## api

HTTP 入口层：

```
main.py
response.py
routers/
```

### main.py

负责：

```
FastAPI 初始化
Config 初始化
Router 注册
Middleware
Exception Handler
Lifecycle
```

### response.py

负责统一：

```
success response
error response
pagination response
```

### routers/

建议先保持：

```
artifacts.py
shares.py
public.py
health.py
```

只负责 HTTP 层，不承载核心业务。

---

# 31. config

```
config/
└── manager.py
```

`manager.py` 负责：

```
加载配置文件
读取环境变量
初始化 Config 对象
配置校验
提供全局配置访问入口
```

例如：

```
Config
├── server
├── database
├── storage
├── auth
└── security
```

---

# 32. artifact_hub

## domain

核心领域模型：

```
Artifact
ArtifactVersion
Share
ShareGrant
```

以及必要枚举：

```
StorageMode
Visibility
Permission
ShareStatus
```

---

## services

承载核心业务：

```
ArtifactService
ShareService
StorageService
```

主要场景：

```
第一次分享
创建新 Version
复用 Version

Local snapshot

NAS prepare
NAS commit

创建 Share
撤销 Share
修改 Share

我分享的
分享给我的

解析分享 Token
```

---

## storage

本期只考虑文件系统。

建议：

```
storage/
├── base.py
├── local.py
└── nas.py
```

不过 Local / NAS 底层实现高度相似，因此也可以：

```
storage/
├── base.py
└── filesystem.py
```

然后通过：

```
StorageMode
root path
```

区分 Local / NAS。

我更推荐后一种，避免重复实现。

---

## repositories

数据库访问通过统一 Repository 接口隔离，当前实现以 SQLite 为默认适配器，并提供 MySQL 适配器，运行时可通过配置切换：

Hub 配置沿用 DataMind `config_objects.py` 的组织方式：`HubConfig.config` 是顶层配置对象，数据库选择位于 `config.storage.mode`，SQLite 参数位于 `config.storage.sqlite`，MySQL 参数位于兼容 DataMind 命名的 `config.storage.server`。

```
ArtifactRepository
ArtifactVersionRepository
ShareRepository
ShareGrantRepository
```

以及对应 ORM / SQL 实现。当前 MVP 将 Artifact、Artifact Version、Share 和 NAS upload 状态集中在 `ArtifactRepository` 下，由 SQLite/MySQL adapter 实现；ShareGrant 仍暂不实现。

---

## auth

负责：

```
Current User
Share Permission
ShareGrant Validation
```

---

## common

放少量基础能力：

```
ID generator
checksum
exceptions
time utilities
```

不要演化成大杂烩。

---

# 33. 本期不做

明确暂不支持：

```
S3 / OSS / MinIO Object API

Presigned URL

Artifact 自动注册

Artifact 编辑

协同编辑

评论

复杂 ACL

Artifact Storage 独立微服务

Session 文件主动同步到 Artifact

跨存储复制
```

---

# 34. V1 范围

```
✓ Session File 分享按钮

✓ Artifact

✓ ArtifactVersion

✓ Share

✓ Local 模式

✓ NAS 模式

✓ Local：Hub copy

✓ NAS：DSH Plugin copy

✓ Checksum Version 复用

✓ 链接分享

✓ VIEW_DOWNLOAD

✓ 有效期

✓ 撤销分享

✓ 我分享的

✓ Share Web

✓ Artifact Preview

✓ Download
```

---

# 35. 最终架构原则

```
1. Agent 生成 Session File 时，不创建 Artifact。

2. 第一次分享时创建 Artifact + ArtifactVersion。

3. Artifact 是逻辑身份。

4. ArtifactVersion 是 immutable snapshot。

5. Share 永远指向 ArtifactVersion。

6. Database 保存 Artifact / Version / Share / Grant。

7. Artifact Storage 保存 Version 文件内容。

8. 本期只支持 Local 和 NAS。

9. Local 模式：
   Hub 可以访问 Session File，
   由 Hub 执行 snapshot/copy。

10. NAS 模式：
    Session File 可以只存在 DSH 本地，
    DSH 直接 copy 到 NAS，
    避免 HTTP 文件上传。

11. NAS 模式下虽然 DSH 搬运 bytes，
    Artifact ID、Version、Storage Key、Share
    仍然由 Hub 统一管理。

12. Artifact Hub 独立于 DSH Pod 生命周期。

13. DSH Plugin 提供创建分享和分享中心。

14. Share Web 面向被分享者提供 Preview / Download。
```

最终数据流可以浓缩成：

```
LOCAL

Session File
    ↓
Hub Copy
    ↓
ArtifactVersion
    ↓
Share


NAS

Session File
    ↓
DSH Copy → NAS
             ↓
            Hub
             ↓
      ArtifactVersion
             ↓
           Share
```
