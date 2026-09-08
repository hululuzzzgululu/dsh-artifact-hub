import {
  CREATED_SHARES_RPC_ENDPOINT,
  LOCAL_SHARE_RPC_CHANNEL,
  LOCAL_SHARE_RPC_ENDPOINT,
  type CreatedShare,
  type LocalShareRequest,
  type LocalShareResult,
  type LocalShareRpcResult,
} from '../contracts.ts'
import { ArtifactHubClient, ArtifactHubRequestError } from './client.ts'
import { createNasShare } from './nas.ts'

/** Artifact byte path selected by the trusted Host configuration. */
export type ShareStorage = {
  readonly mode: 'local'
} | {
  readonly mode: 'nas'
  readonly artifactRoot: string
}

const LOCAL_STORAGE: ShareStorage = { mode: 'local' }

/** RPC registration contract exposed by the DSH Host connection. */
export interface HostConnectionRpc {
  handle(
    channel: string,
    handler: (
      endpoint: string,
      payload: unknown,
      signal: AbortSignal,
    ) => Promise<LocalShareRpcResult<unknown>>,
    options: { readonly authority: 'loopback' },
  ): () => Promise<void>
}

/** Trusted Host-side face of DSH's live session store. */
export interface HostSessionStore {
  readonly get: (sessionId: string) => {
    readonly header: { readonly cwd?: string }
  } | undefined
}

/** Host-side subset of DSH's workspace registry used to enrich Artifacts. */
export interface HostWorkspaceRegistry {
  readonly list: () => readonly {
    readonly id: string
    readonly path: string
    readonly title: string
    readonly sessionIds: readonly unknown[]
  }[]
}

/** Register the browser-facing share RPC channel for the configured storage mode. */
export function registerShareRoute(
  rpc: HostConnectionRpc,
  client: ArtifactHubClient,
  sessions: HostSessionStore,
  workspaces: HostWorkspaceRegistry,
  storage: ShareStorage,
): () => Promise<void> {
  return rpc.handle(
    LOCAL_SHARE_RPC_CHANNEL,
    (endpoint, payload, signal) => {
      if (endpoint === LOCAL_SHARE_RPC_ENDPOINT) {
        return handleShareRequest(payload, client, sessions, workspaces, storage, signal)
      }
      if (endpoint === CREATED_SHARES_RPC_ENDPOINT) {
        return handleCreatedSharesRequest(client, signal)
      }
      return Promise.resolve(failure('bad-request', `Unknown Artifact Hub endpoint: ${endpoint}`))
    },
    { authority: 'loopback' },
  )
}

/** Backwards-compatible registration helper for callers pinned to Local mode. */
export function registerLocalShareRoute(
  rpc: HostConnectionRpc,
  client: ArtifactHubClient,
  sessions: HostSessionStore,
  workspaces: HostWorkspaceRegistry,
): () => Promise<void> {
  return registerShareRoute(rpc, client, sessions, workspaces, LOCAL_STORAGE)
}

/** List Shares through the same trusted Host identity used for creation. */
export async function handleCreatedSharesRequest(
  client: ArtifactHubClient,
  signal?: AbortSignal,
): Promise<LocalShareRpcResult<readonly CreatedShare[]>> {
  try {
    return { ok: true, value: await client.listCreatedShares(signal) }
  } catch (error: unknown) {
    if (error instanceof ArtifactHubRequestError) {
      return failure(error.status >= 400 && error.status < 500 ? 'bad-request' : 'internal', error.message)
    }
    return failure('internal', messageOf(error))
  }
}

/** Validate one browser request and publish it through the configured storage mode. */
export async function handleShareRequest(
  payload: unknown,
  client: ArtifactHubClient,
  sessions: HostSessionStore,
  workspaces: HostWorkspaceRegistry,
  storage: ShareStorage,
  signal?: AbortSignal,
): Promise<LocalShareRpcResult<LocalShareResult>> {
  try {
    const input = parseRequest(payload)
    const workspaceRoot = sessions.get(input.sessionId)?.header.cwd
    if (workspaceRoot === undefined || workspaceRoot === '') {
      throw new LocalShareRouteError(
        'session-not-found',
        'Session workspace is unavailable',
        { sessionId: input.sessionId },
      )
    }
    const registeredWorkspaces = workspaces.list()
    const workspace = registeredWorkspaces.find(candidate =>
      candidate.sessionIds.some(sessionId => String(sessionId) === input.sessionId),
    )
    const request = {
      ...input,
      workspaceRoot,
      dshWorkspacePath: workspace?.path ?? workspaceRoot,
      ...(workspace === undefined
        ? {}
        : {
            dshWorkspaceId: String(workspace.id),
            dshWorkspaceTitle: workspace.title,
          }),
    }
    const result = storage.mode === 'nas'
      ? await createNasShare(client, request, storage.artifactRoot, signal)
      : await client.createLocalShare(request, signal)
    return { ok: true, value: result }
  } catch (error: unknown) {
    if (error instanceof LocalShareRouteError) {
      return failure(error.code, error.message, error.details)
    }
    if (error instanceof ArtifactHubRequestError) {
      return failure(error.status >= 400 && error.status < 500 ? 'bad-request' : 'internal', error.message)
    }
    return failure('bad-request', messageOf(error))
  }
}

/** Backwards-compatible request helper for tests and Local-only integrations. */
export async function handleLocalShareRequest(
  payload: unknown,
  client: ArtifactHubClient,
  sessions: HostSessionStore,
  workspaces: HostWorkspaceRegistry,
  signal?: AbortSignal,
): Promise<LocalShareRpcResult<LocalShareResult>> {
  return handleShareRequest(payload, client, sessions, workspaces, LOCAL_STORAGE, signal)
}

class LocalShareRouteError extends Error {
  constructor(
    readonly code: 'session-not-found',
    message: string,
    readonly details: Readonly<Record<string, unknown>>,
  ) {
    super(message)
    this.name = 'LocalShareRouteError'
  }
}

function parseRequest(value: unknown): LocalShareRequest {
  if (!isRecord(value)) throw new Error('Request body must be an object')
  const sessionId = nonBlank(value.sessionId, 'sessionId')
  const sourcePath = nonBlank(value.sourcePath, 'sourcePath')
  if (sourcePath.startsWith('/')
    || sourcePath.startsWith('\\')
    || /^[A-Za-z]:[\\/]/u.test(sourcePath)
    || hasParentSegment(sourcePath)) {
    throw new Error('sourcePath must be relative to the Session workspace')
  }
  const expiresAt = optionalString(value.expiresAt, 'expiresAt')
  if (expiresAt !== undefined && Number.isNaN(Date.parse(expiresAt))) {
    throw new Error('expiresAt must be an ISO-8601 timestamp')
  }
  const artifactId = optionalString(value.artifactId, 'artifactId')
  return {
    sessionId,
    sourcePath,
    ...(expiresAt === undefined ? {} : { expiresAt }),
    ...(artifactId === undefined ? {} : { artifactId }),
  }
}

function nonBlank(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim() === '') throw new Error(`${field} is required`)
  return value
}

function optionalString(value: unknown, field: string): string | undefined {
  if (value === undefined) return undefined
  return nonBlank(value, field)
}

function hasParentSegment(path: string): boolean {
  return path.split(/[\\/]+/u).includes('..')
}

function failure(
  code: 'bad-request' | 'session-not-found' | 'internal',
  message: string,
  details: Readonly<Record<string, unknown>> = code === 'bad-request' ? { issues: [] } : {},
): LocalShareRpcResult<never> {
  return { ok: false, error: { code, message, details } }
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
