# DeepSeek Harness 的 Artifact Hub

简体中文 | [English](README.md)

Artifact Hub 把 DSH（DeepSeek Harness）会话中 Agent 生成的可变文件，固化为不可变、可分享的 Artifact Version —— 通过公开链接分享，且与原会话的生命周期解耦。

```
Agent 生成文件 → 点击 [分享] → 固化不可变版本快照 → 生成分享链接 → 任何人在线查看 / 下载
```

## 为什么需要它

DSH 会话中，Agent 会在 session workspace 里产出各种文件 —— SQL、HTML、Markdown、PDF、图片等。目前想分享其中一个文件，只能分享整个 Session，或者下载后通过 IM / 邮件再次发送。

Artifact Hub 为文件提供独立的分享生命周期：

- **分享的是文件，不是会话。** 原会话关闭或清理后，分享链接依然有效。
- **版本不可变。** 分享时对文件做快照。Agent 后续继续修改，再次分享会创建下一个版本 —— 已分享出去的链接内容永不变化。
- **可撤销、可设有效期。** 每个分享都可以撤销或设置截止时间。
- **安全的预览。** 公开查看页支持渲染 Markdown、代码、JSON、图片、PDF 和沙箱 HTML —— 不可信的 Agent HTML 无法触碰 DSH。

## 这是一个服务套件，不是单个插件

只有 DSH 插件本身什么都做不了。它是三件套系统中的一环 —— 请按运行整套服务来规划：

```
                         User
                          │
                 ┌────────┴────────┐
                 ▼                 ▼
               DSH             Share Web          ← 访客看到的页面
                │                 │
                └───────┬─────────┘
                        ▼
                 Artifact Hub                  ← 大脑
                        │
             ┌──────────┴───────────┐
             ▼                      ▼
          Database           Artifact Storage
                                  │
                           ┌──────┴──────┐
                           ▼             ▼
                         Local           NAS
```

| 组件 | 路径 | 职责 | 运行形态 |
|---|---|---|---|
| **Hub** | [`hub/`](hub/) | 后端。管理 Artifact、Version、Share、存储路径、checksum、token 和全部生命周期规则。FastAPI + SQLite（默认）或 MySQL。 | Python 服务 |
| **DSH 插件** | [`plugins/dsh-artifact-hub/`](plugins/dsh-artifact-hub/) | DSH 内的 UI：文件旁的 [分享] 按钮和分享中心侧边栏。向 Hub 转发可信的 workspace 元数据。 | 运行在 DSH 内 |
| **Share Web** | [`apps/share-web/`](apps/share-web/) | `/s/{token}` 的公开查看页：预览、下载、过期/撤销提示。 | Nginx 后的静态站点 |
| **部署配置** | [`deploy/`](deploy/) | 公开边界与服务定义：Nginx 路由、systemd unit。 | Nginx / systemd |

## 核心模型

```
Session File ──首次分享──▶ Artifact ──快照──▶ ArtifactVersion ──链接──▶ Share
（可变，                       （逻辑              （不可变，             （可撤销，
 随会话消亡）                    身份）              有 checksum）          可设有效期）
```

- 文件只有在用户分享时才成为 **Artifact**。Agent 正常输出不创建任何记录。
- 每个 **ArtifactVersion** 都是不可变快照；checksum 一致时复用已有版本。
- **Share** 永远指向某个版本 —— 而不是会话中的活文件。每个版本最多一个 Share；再次分享会替换链接，旧链接随即失效。

术语的精确定义见 [`CONTEXT.md`](CONTEXT.md)；完整设计见 [`docs/overview.md`](docs/overview.md)。

## 存储模式

两种文件系统模式；搬运 bytes 的角色不同，但 Artifact 身份、版本、存储路径和 Share 始终由 Hub 管理。

| | Local | NAS |
|---|---|---|
| Hub 能读到 Session File | 能 | 通常不能（在 DSH 机器上） |
| Artifact 存储 | Hub 本地磁盘 | 共享 NAS 挂载 |
| 谁复制文件 | Hub | DSH 插件 |
| 文件是否走 HTTP | 否 | 否 |

**Local** —— Hub 和 DSH 能看到同一文件系统。插件只传引用；Hub 自己读取、计算 checksum 并复制快照。

**NAS** —— Session File 在 DSH 本地机器上，但双方都挂载了 NAS。两阶段协议避免 HTTP 上传中转：Hub 先 `prepare` 分配存储路径，插件直接把文件复制到 NAS，Hub 校验后 `commit`。

## 快速开始

前置要求：`uv`、`node`、`pnpm`、`dsh` CLI、`curl`、`lsof`。

仓库根目录的一个脚本驱动整套服务：

```bash
./scripts/dev.sh setup  # 安装依赖、构建并把插件装入 DSH profile
./scripts/dev.sh test   # 三个子项目的测试、类型检查和构建
./scripts/dev.sh start  # 启动 Hub + share-web + DSH Web，并执行 smoke test
```

`start` 在前台运行全部三个服务（Ctrl-C 一并停止）：

| 服务 | 默认地址 |
|---|---|
| Hub | http://127.0.0.1:8000 |
| Share Web | http://127.0.0.1:5173 |
| DSH Web | http://127.0.0.1:3080 |

复制 `scripts/dev.env.example` 为 `scripts/dev.env` 可覆盖端口和路径。之后在 DSH 会话中，点击任意生成文件旁的 **[分享]** 即可。

`dev.sh` 仅用于开发。真正的部署 —— Hub 作为 systemd 服务、Share Web 与公开 API 走 Nginx、配置 TLS、插件指向 Hub 内网地址 —— 见[部署指南](docs/deployment.md)（英文）。

## 仓库结构

```
├── hub/                    # Python 后端（FastAPI，uv）
│   ├── src/api/            #   HTTP 层：routers、responses
│   ├── src/artifact_hub/   #   领域模型、服务、存储、repositories
│   └── sqls/               #   表结构
├── plugins/dsh-artifact-hub/
│   └── src/
│       ├── host/           #   可信的 Host 侧 RPC（workspace 解析）
│       └── client/         #   分享按钮、分享中心 UI
├── apps/share-web/         # 公开查看页（Vite SPA）
├── deploy/nginx/           # 生产环境路由配置
├── docs/                   # 设计文档、ADR、调研、协作约定
└── scripts/                # dev.sh 等
```

## 安全设计

- 分享 token 只保存 SHA-256 hash；原始 token 仅在创建时返回一次。
- 管理 API 只对 DSH Host 开放；浏览器无法提供 workspace 根路径或创建者身份。
- 公开内容响应使用 `no-store`、`nosniff` 和 CSP sandbox；Agent HTML 在沙箱 iframe 中渲染，与 DSH 的 Cookie 和 API 隔离。
- Nginx 不记录含 token 的 URL 访问日志。

## 范围

**V1：** 链接分享（`LINK` + 查看和下载）、Local 与 NAS 存储、基于 checksum 的版本复用、有效期、撤销、分享中心（我分享的）、公开预览和下载。

**暂不支持：** 对象存储（S3/OSS/MinIO）、presigned URL、组织内/指定用户分享、ShareGrant 与"分享给我的"、认证、评论、编辑。

## 文档

- [`docs/`](docs/) — 全部文档索引
- [`docs/overview.md`](docs/overview.md) — 完整概要设计
- [`docs/adr/`](docs/adr/) — 架构决策记录
- [`hub/README.md`](hub/README.md) — Hub API、配置、数据库迁移
- [`plugins/dsh-artifact-hub/README.md`](plugins/dsh-artifact-hub/README.md) — 插件安装与数据流
- [`apps/share-web/README.md`](apps/share-web/README.md) — 查看页开发与构建

## 参与贡献

见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。Issue 与 spec 以 Markdown 文件记录在 `.scratch/` 下，该目录设计为仅保留在本地（见 [issue tracker 约定](docs/agents/issue-tracker.md)）。

## 许可证

[MIT](LICENSE)
