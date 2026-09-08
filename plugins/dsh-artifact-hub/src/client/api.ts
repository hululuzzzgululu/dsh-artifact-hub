import {
  CREATED_SHARES_RPC_ENDPOINT,
  LOCAL_SHARE_RPC_CHANNEL,
  LOCAL_SHARE_RPC_ENDPOINT,
  type CreatedShare,
  type LocalShareRequest,
  type LocalShareResult,
  type LocalShareRpcResult,
} from '../contracts.ts'

/** Browser RPC subset exposed by DSH's client Connection service. */
export interface ClientConnectionRpc {
  call(
    channel: string,
    endpoint: string,
    payload: unknown,
    signal?: AbortSignal,
  ): Promise<LocalShareRpcResult<unknown>>
}

/** UI-bound request function passed into the sharing components. */
export type LocalShareRequester = (
  request: LocalShareRequest,
  signal?: AbortSignal,
) => Promise<LocalShareResult>

/** UI-bound creator's-share list function passed into the sharing components. */
export type CreatedSharesRequester = (
  signal?: AbortSignal,
) => Promise<readonly CreatedShare[]>

/** List Shares created by the Host's trusted identity. */
export async function requestCreatedShares(
  rpc: ClientConnectionRpc,
  signal?: AbortSignal,
): Promise<readonly CreatedShare[]> {
  const result = await rpc.call(
    LOCAL_SHARE_RPC_CHANNEL,
    CREATED_SHARES_RPC_ENDPOINT,
    {},
    signal,
  )
  if (!result.ok) throw new Error(result.error.message)
  if (!Array.isArray(result.value) || !result.value.every(isCreatedShare)) {
    throw new Error('DSH Host returned an invalid created-share list')
  }
  return result.value
}

/** Request one Local snapshot through DSH's version-stable Connection RPC. */
export async function requestLocalShare(
  request: LocalShareRequest,
  rpc: ClientConnectionRpc,
  signal?: AbortSignal,
): Promise<LocalShareResult> {
  const result = await rpc.call(
    LOCAL_SHARE_RPC_CHANNEL,
    LOCAL_SHARE_RPC_ENDPOINT,
    request,
    signal,
  )
  if (!result.ok) throw new Error(result.error.message)
  const value = result.value
  if (!isShareResult(value)) throw new Error('DSH Host returned an invalid share result')
  return value
}

function isShareResult(value: unknown): value is LocalShareResult {
  return isRecord(value)
    && typeof value.shareId === 'string'
    && typeof value.artifactId === 'string'
    && typeof value.artifactVersionId === 'string'
    && typeof value.version === 'number'
    && Number.isInteger(value.version)
    && typeof value.name === 'string'
    && typeof value.url === 'string'
    && (value.expiresAt === null || typeof value.expiresAt === 'string')
}

function isCreatedShare(value: unknown): value is CreatedShare {
  return isRecord(value)
    && typeof value.shareId === 'string'
    && typeof value.artifactId === 'string'
    && typeof value.artifactVersionId === 'string'
    && typeof value.version === 'number'
    && Number.isInteger(value.version)
    && typeof value.name === 'string'
    && typeof value.sourceSessionId === 'string'
    && typeof value.sourcePath === 'string'
    && typeof value.mimeType === 'string'
    && typeof value.size === 'number'
    && Number.isFinite(value.size)
    && value.visibility === 'LINK'
    && value.permission === 'VIEW_DOWNLOAD'
    && typeof value.createdAt === 'string'
    && (value.expiresAt === null || typeof value.expiresAt === 'string')
    && (value.revokedAt === null || typeof value.revokedAt === 'string')
    && (value.previewUrl === null || typeof value.previewUrl === 'string')
    && (value.shareUrl === null || typeof value.shareUrl === 'string')
}

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
