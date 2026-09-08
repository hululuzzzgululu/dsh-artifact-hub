# dsh-artifact-hub plugin

DeepSeek Harness 的 Artifact Hub 插件。当前版本支持 `LOCAL` 和 `NAS`：在一轮对话产生的文件旁显示“分享”，并在左侧“新会话”下提供“分享中心”入口。DSH Host 从可信的 session 与 workspace 服务解析源文件和创建者元数据；Local 模式由 Hub 复制快照，NAS 模式由 DSH Host 直接复制到共享挂载后让 Hub 校验并提交。

## 前置条件

- Local 模式下，DSH Host 与 Artifact Hub 必须能以相同绝对路径访问 session 的 `header.cwd` workspace。
- NAS 模式下，DSH Host 必须能读取 session workspace，且 DSH Host 与 Hub 都要挂载同一 NAS；两边的挂载路径可以不同，但权限必须允许 DSH 创建文件、Hub 读取文件。
- Artifact Hub 已启动，默认地址为 `http://127.0.0.1:8000`。
- DSH 版本支持 bundle、`dsh.client` Web 插件、`conversation.chat.turnTail` 插槽和 Host `workspaceRegistry` 服务（当前开发预览版）。

## 安装

在仓库根目录执行：

```bash
dsh plugin --profile web add ./plugins/dsh-artifact-hub
```

从 DSH 源码运行时使用：

```bash
pnpm dsh plugin --profile web add ./plugins/dsh-artifact-hub
pnpm dsh web
```

插件通过以下环境变量配置：

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `DSH_ARTIFACT_HUB_URL` | `http://127.0.0.1:8000` | Hub 服务地址 |
| `DSH_ARTIFACT_HUB_MODE` | `local` | Artifact 文件流：`local` 或 `nas` |
| `DSH_ARTIFACT_HUB_ARTIFACT_ROOT` | — | NAS 模式必填；DSH Host 上已存在、可写的 NAS Artifact 根目录 |
| `DSH_ARTIFACT_HUB_CREATED_BY_ID` | `dsh-local-user` | 写入 Artifact/Version/Share 的可信创建者 ID |
| `DSH_ARTIFACT_HUB_CREATED_BY_NAME` | 与 ID 相同 | 创建者展示名称 |
| `DSH_ARTIFACT_HUB_CREATED_BY` | — | 旧版 ID 配置兼容项；新配置应使用 `..._ID` |

例如：

```bash
DSH_ARTIFACT_HUB_URL=http://artifact-hub:8000 \
DSH_ARTIFACT_HUB_MODE=nas \
DSH_ARTIFACT_HUB_ARTIFACT_ROOT=/mnt/dsh-nas/artifacts \
DSH_ARTIFACT_HUB_CREATED_BY_ID=user-001 \
DSH_ARTIFACT_HUB_CREATED_BY_NAME='Alice' \
dsh web
```

## Local 数据流

1. DSH Client 从本轮成功写入的文件列表取得 `sessionId` 和相对 `sourcePath`。
2. 浏览器通过 DSH Connection RPC 调用 `/artifact-hub` channel 的 `shares` endpoint；浏览器不能指定 workspace 或创建者元数据。
3. DSH Host 使用 `ctx.sessions.get(sessionId).header.cwd` 解析可信文件根目录，并在 `ctx.workspaceRegistry.list()` 中按 Session 成员关系取得 Workspace 的 `id/path/title`；未注册的旧 Session 只回退路径。Host 再按 `source_path` 扩展名推断 `artifact_type`（html/markdown/text/code/data/image/pdf/archive/other），加入受信任身份字段后调用 Hub 的 `POST /api/shares`。
4. Hub 从 `<workspace_root>/<source_path>` 读取文件；同一来源会复用 Artifact，checksum 未变化时也会复用 Artifact Version，并对该版本唯一的 Share 做幂等更新：复用原 token，仅更新有效期，旧链接保持有效（原 Share 已撤销时才换新 token）。插件只把分享 URL 返回浏览器，不返回原始 token 字段。

## NAS 数据流

1. DSH Host 将可信 Session/Workspace 元数据发送到 Hub 的 `POST /api/shares/prepare`，取得 `upload_id` 和相对 `storage_key`。
2. Host 校验源文件仍位于 Session workspace 内，用自己的 `DSH_ARTIFACT_HUB_ARTIFACT_ROOT + storage_key` 计算 NAS 路径；Hub 返回的绝对 `target_path` 不参与计算，因此两台机器可使用不同挂载点。
3. Host 在 NAS 目标目录内写临时文件，同时计算 SHA-256，完成后原子替换为最终文件。
4. Host 调用 `POST /api/shares/commit`；Hub 从自己的 NAS 挂载重新读取文件、核对 checksum/size，并创建 Artifact Version 与 Share。

“分享中心”通过同一条 loopback-only RPC 从 Host 查询可信 `createdById` 对应的分享记录，并按 `artifactId` 汇总各版本的唯一 Share。浏览器不提交创建者身份，也不会收到 storage key 或 checksum；Hub 为仍然有效的记录签发 10 分钟短时预览 URL 供“预览”跳转，另返回从落库 token 重建的持久分享链接（`shareUrl`）。分享弹窗打开时会查询当前文件是否已有有效分享：已有则保留完整表单（分享方式、权限、可编辑的到期时间，均回填），仅把底部按钮换成“复制链接/打开链接”且不再展示链接本身——修改到期时间后点击任一按钮会先通过幂等接口保存（token 不变）再复制/打开；仅撤销过的文件回退到全新表单。页面支持文件/版本/Share ID 搜索与状态筛选，控件使用 DSH 主题变量，可随明暗主题切换。

当前分享方式固定为“获得链接的任何人”（`LINK`），权限固定为“查看和下载”（`VIEW_DOWNLOAD`）；弹窗可选设置有效期。组织内分享、指定用户分享、ShareGrant 和“分享给我的”视图尚未实现。

## 开发验证

```bash
cd plugins/dsh-artifact-hub
pnpm install
pnpm run typecheck
pnpm test
pnpm run build
```
