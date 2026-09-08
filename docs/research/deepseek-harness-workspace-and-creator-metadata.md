# DeepSeek Harness 的 Workspace 与创建者元数据

调研对象：本地 `deepseek-harness` checkout，commit `d347e703908d0406b7a7ef80e3a0e594d86b2215`（调研时工作树干净）。以下结论只基于该 checkout 的主源码和随源码维护的包文档。

## 结论

Host 插件可以取得已归组 Session 所属 Workspace 的 `id`、`path` 和 `title`。`@deepseek-ai/dsh-workspace` 把服务注册为 `ctx.workspaceRegistry`；消费插件需要声明 `workspaceRegistry` 注入。Web App 的标准 bundle 已挂载该服务，但 headless/minimal composition 可以不挂载，因此这不是所有 Harness composition 都必然存在的能力。[[Context 注册](../../../../opensources/deepseek-harness/packages/workspace/workspace/src/index.ts#L66-L70)] [[Web App 挂载](../../../../opensources/deepseek-harness/packages/bundle/web-app/cordis.patch.yml#L61-L62)] [[可选性说明](../../../../opensources/deepseek-harness/packages/workspace/workspace/README.md#L10-L12)]

`Workspace` 公共接口直接暴露稳定 UUID `id`、经 `fs.realpath` 规范化的 `path`、显示用 `title` 和 `sessionIds`；Registry 提供同步的 `list()`、按 ID 的 `get()`，以及仅按目录所有权查询的异步 `resolveByPath()`。[[Workspace 字段](../../../../opensources/deepseek-harness/packages/workspace/workspace/src/types.ts#L25-L59)] [[Registry 查询 API](../../../../opensources/deepseek-harness/packages/workspace/workspace/src/index.ts#L165-L188)] [[按路径查询](../../../../opensources/deepseek-harness/packages/workspace/workspace/src/index.ts#L269-L282)]

推荐按下面的含义解析并上送 Artifact 元数据：

| Artifact 字段 | 已归组 Session | 未归组 Session |
|---|---|---|
| `dsh_workspace_id` | `String(workspace.id)` | `NULL` / 省略 |
| `dsh_workspace_path` | `workspace.path` | 回退到 `session.header.cwd` |
| `dsh_workspace_title` | `workspace.title` | `NULL` / 省略；不要伪造为注册 Workspace 标题 |

核心查找应为 `ctx.workspaceRegistry.list().find(workspace => workspace.sessionIds.includes(sessionId))`。当前 API 没有 `getBySessionId()`，所以这是 O(Workspace 数量) 的 Host 内存扫描；通常无需 I/O，因为 `list()` 返回 Registry 的同步投影。[[`list()` 语义](../../../../opensources/deepseek-harness/packages/workspace/workspace/src/index.ts#L174-L188)]

## 为什么不能仅用 `header.cwd` 反查 Workspace

Workspace 成员关系不是“路径相同”这么简单，而是“Workspace 记录显式拥有该 Session ID，且 Session header 的规范化 cwd 仍等于 Workspace path”。`sessionIds` getter 会按这个条件过滤；attach 时也会拒绝 cwd 缺失、路径失效、非目录或路径不匹配的 Session。[[成员关系定义](../../../../opensources/deepseek-harness/packages/workspace/workspace/src/types.ts#L25-L29)] [[读取时过滤](../../../../opensources/deepseek-harness/packages/workspace/workspace/src/entity.ts#L101-L103)] [[attach 校验](../../../../opensources/deepseek-harness/packages/workspace/workspace/src/entity.ts#L109-L149)]

Registry 还保证一个 Session 最多只被一个 Workspace 记录拥有。[[状态校验](../../../../opensources/deepseek-harness/packages/workspace/workspace/src/index.ts#L528-L549)]

因此，`resolveByPath(session.header.cwd)` 不能作为 Session→Workspace 的兜底：它只回答“哪个 Workspace 注册了这个目录”，不回答“Session 是否属于它”。Session 可以通过 `detachSession()` 主动解除归组；删除 Workspace 也会保留 Session，使其变成 ungrouped；同一路径以后重新注册时会得到一个空的新 Workspace。此时按 cwd 反查会把旧 Session 错归到新 Workspace。[[解除归组](../../../../opensources/deepseek-harness/packages/workspace/workspace/src/entity.ts#L174-L178)] [[删除后的语义](../../../../opensources/deepseek-harness/packages/workspace/workspace/README.md#L62-L68)] [[重新注册为空](../../../../opensources/deepseek-harness/packages/workspace/workspace/README.md#L153-L164)]

`header.cwd` 适合只作为未归组 Session 的 `dsh_workspace_path` 回退值。它在 `SessionHeader` 中是可选的绝对路径，不含 Workspace id/title。若当前 Session 是 live，可从 `ctx.sessions.get(id)?.header.cwd` 读取；但 `SessionStore.get()` 明确只查 live Session。要覆盖 cold/仅持久化的未归组 Session，需要额外注入 `sessionPersistence` 并调用 `stat(id)` 读取轻量 header。[[SessionHeader](../../../../opensources/deepseek-harness/packages/core/session/src/types.ts#L88-L128)] [[live-only 查询](../../../../opensources/deepseek-harness/packages/core/session/src/index.ts#L1145-L1160)] [[持久化 header 查询](../../../../opensources/deepseek-harness/packages/session/session-persistence/src/index.ts#L176-L197)]

可采用如下解析顺序：

```ts
const workspace = ctx.workspaceRegistry
  .list()
  .find(candidate => candidate.sessionIds.includes(sessionId))

if (workspace) {
  return {
    dshWorkspaceId: String(workspace.id),
    dshWorkspacePath: workspace.path,
    dshWorkspaceTitle: workspace.title,
  }
}

// live 请求：ctx.sessions.get(sessionId)?.header.cwd
// cold-safe 请求：await ctx.sessionPersistence.stat(sessionId)?.header.cwd
return { dshWorkspacePath: header.cwd } // id/title 保持缺失
```

## 创建者 ID 与名称

Harness 的 `SessionHeader` 没有创建人、账号或显示名字段；目前 identity 子系统也只有一个 anonymous-user-id 包。它提供 `getOrCreateAnonymousUserId()`：返回按 `$DSH_HOME` 持久化的随机 UUID，能稳定标识一个 Harness home，但明确不标识真实用户。[[SessionHeader 完整字段](../../../../opensources/deepseek-harness/packages/core/session/src/types.ts#L91-L128)] [[identity 子系统范围](../../../../opensources/deepseek-harness/packages/identity/README.md#L10-L25)] [[匿名 ID 实现](../../../../opensources/deepseek-harness/packages/identity/anonymous-user-id/src/index.ts#L25-L29)] [[读取 API](../../../../opensources/deepseek-harness/packages/identity/anonymous-user-id/src/index.ts#L57-L99)]

据此，当前 Harness 能提供的通用默认值是：

- `created_by_id = String(getOrCreateAnonymousUserId())`；
- Harness 没有对应的创建者名称能力，因此 `created_by_name = created_by_id`；
- 若部署层已经有可信的认证用户 ID/名称，应由部署配置或认证边界显式传入，而不是把 anonymous user id 描述为真人账号。

