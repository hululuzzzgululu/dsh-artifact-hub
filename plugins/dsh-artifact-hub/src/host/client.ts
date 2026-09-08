import type {
  CreatedShare,
  LocalShareRequest,
  LocalShareResult,
} from '../contracts.ts'

/** Trusted identity fields added by the DSH Host instead of the browser. */
export interface ArtifactHubIdentity {
  readonly createdById: string
  readonly createdByName: string
}

/** Browser request enriched with the workspace resolved by the trusted Host. */
export interface TrustedLocalShareRequest extends LocalShareRequest {
  readonly workspaceRoot: string
  readonly dshWorkspaceId?: string
  readonly dshWorkspacePath: string
  readonly dshWorkspaceTitle?: string
}

/** Injectable Fetch subset used by the Artifact Hub HTTP adapter. */
export type Fetch = (input: string | URL, init?: RequestInit) => Promise<Response>

interface HubEnvelope {
  readonly resultCode: string
  readonly resultMsg: string
  readonly resultObj: unknown
}

interface HubShareResult {
  readonly share_id: string
  readonly artifact_id: string
  readonly artifact_version_id: string
  readonly version: number
  readonly name: string
  readonly url: string
  readonly expires_at: string | null
}

interface HubCreatedShare {
  readonly share_id: string
  readonly artifact_id: string
  readonly artifact_version_id: string
  readonly version: number
  readonly name: string
  readonly source_session_id: string
  readonly source_path: string
  readonly mime_type: string
  readonly size: number
  readonly visibility: 'LINK'
  readonly permission: 'VIEW_DOWNLOAD'
  readonly created_at: string
  readonly expires_at: string | null
  readonly revoked_at: string | null
  readonly url: string | null
  readonly share_url: string | null
}

/** Error returned when the Artifact Hub rejects or cannot satisfy a request. */
export class ArtifactHubRequestError extends Error {
  /** @param status HTTP status to expose through the DSH Host route. */
  constructor(readonly status: number, message: string) {
    super(message)
    this.name = 'ArtifactHubRequestError'
  }
}

/** Coarse artifact classification derived from the Session file extension. */
const ARTIFACT_TYPES: Readonly<Record<string, string>> = {
  html: 'html', htm: 'html',
  md: 'markdown', markdown: 'markdown',
  txt: 'text', log: 'text',
  csv: 'data', tsv: 'data', json: 'data', jsonl: 'data', xlsx: 'data', parquet: 'data',
  png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', svg: 'image', webp: 'image',
  bmp: 'image', ico: 'image',
  pdf: 'pdf',
  zip: 'archive', tar: 'archive', gz: 'archive', tgz: 'archive', '7z': 'archive',
  js: 'code', jsx: 'code', ts: 'code', tsx: 'code', py: 'code', sql: 'code',
  java: 'code', go: 'code', rs: 'code', c: 'code', h: 'code', cpp: 'code',
  sh: 'code', rb: 'code', php: 'code',
}

/** Infer the Hub's artifact_type from a Session file path. */
export function inferArtifactType(sourcePath: string): string {
  const name = sourcePath.split(/[\\/]+/u).pop() ?? ''
  const dot = name.lastIndexOf('.')
  if (dot < 1 || dot === name.length - 1) return 'other'
  return ARTIFACT_TYPES[name.slice(dot + 1).toLowerCase()] ?? 'other'
}

/** Minimal Local-mode client for Artifact Hub's single-stage share endpoint. */
export class ArtifactHubClient {
  private readonly sharesUrl: URL

  /**
   * @param serviceUrl Artifact Hub public or service base URL.
   * @param identity trusted creator identity.
   * @param fetcher HTTP implementation, injectable for tests.
   */
  constructor(
    serviceUrl: string,
    private readonly identity: ArtifactHubIdentity,
    private readonly fetcher: Fetch = fetch,
  ) {
    this.sharesUrl = new URL('/api/shares', withTrailingSlash(serviceUrl))
  }

  /** Create one immutable Local snapshot and return a browser-safe result. */
  async createLocalShare(
    request: TrustedLocalShareRequest,
    signal?: AbortSignal,
  ): Promise<LocalShareResult> {
    let response: Response
    try {
      response = await this.fetcher(this.sharesUrl, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          session_id: request.sessionId,
          workspace_root: request.workspaceRoot,
          source_path: request.sourcePath,
          artifact_type: inferArtifactType(request.sourcePath),
          created_by_id: this.identity.createdById,
          created_by_name: this.identity.createdByName,
          dsh_workspace_path: request.dshWorkspacePath,
          ...(request.dshWorkspaceId === undefined ? {} : { dsh_workspace_id: request.dshWorkspaceId }),
          ...(request.dshWorkspaceTitle === undefined ? {} : { dsh_workspace_title: request.dshWorkspaceTitle }),
          ...(request.artifactId === undefined ? {} : { artifact_id: request.artifactId }),
          ...(request.expiresAt === undefined ? {} : { expires_at: request.expiresAt }),
        }),
        ...(signal === undefined ? {} : { signal }),
      })
    } catch (error: unknown) {
      if (signal?.aborted === true) throw error
      throw new ArtifactHubRequestError(502, `Artifact Hub is unavailable: ${messageOf(error)}`)
    }

    const envelope = await readEnvelope(response)
    if (!response.ok) {
      throw new ArtifactHubRequestError(response.status, envelope.resultMsg)
    }
    return parseShareResult(envelope.resultObj)
  }

  /** List only browser-safe metadata for Shares owned by the trusted identity. */
  async listCreatedShares(signal?: AbortSignal): Promise<readonly CreatedShare[]> {
    const url = new URL(this.sharesUrl)
    url.searchParams.set('created_by_id', this.identity.createdById)
    let response: Response
    try {
      response = await this.fetcher(url, {
        method: 'GET',
        ...(signal === undefined ? {} : { signal }),
      })
    } catch (error: unknown) {
      if (signal?.aborted === true) throw error
      throw new ArtifactHubRequestError(502, `Artifact Hub is unavailable: ${messageOf(error)}`)
    }
    const envelope = await readEnvelope(response)
    if (!response.ok) {
      throw new ArtifactHubRequestError(response.status, envelope.resultMsg)
    }
    if (!isRecord(envelope.resultObj) || !Array.isArray(envelope.resultObj.items)) {
      throw new ArtifactHubRequestError(502, 'Artifact Hub returned an invalid created-share list')
    }
    return envelope.resultObj.items.map(parseCreatedShare)
  }
}

function withTrailingSlash(value: string): string {
  return value.endsWith('/') ? value : `${value}/`
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

async function readEnvelope(response: Response): Promise<HubEnvelope> {
  let value: unknown
  try {
    value = await response.json() as unknown
  } catch {
    throw new ArtifactHubRequestError(
      502,
      `Artifact Hub returned non-JSON content (HTTP ${String(response.status)})`,
    )
  }
  if (!isRecord(value)
    || typeof value.resultCode !== 'string'
    || typeof value.resultMsg !== 'string'
    || !('resultObj' in value)) {
    throw new ArtifactHubRequestError(502, 'Artifact Hub returned an invalid response envelope')
  }
  return {
    resultCode: value.resultCode,
    resultMsg: value.resultMsg,
    resultObj: value.resultObj,
  }
}

function parseShareResult(value: unknown): LocalShareResult {
  if (!isRecord(value)
    || typeof value.share_id !== 'string'
    || typeof value.artifact_id !== 'string'
    || typeof value.artifact_version_id !== 'string'
    || typeof value.version !== 'number'
    || !Number.isInteger(value.version)
    || typeof value.name !== 'string'
    || typeof value.url !== 'string'
    || (value.expires_at !== null && typeof value.expires_at !== 'string')) {
    throw new ArtifactHubRequestError(502, 'Artifact Hub returned an invalid share result')
  }
  const result = value as unknown as HubShareResult
  return {
    shareId: result.share_id,
    artifactId: result.artifact_id,
    artifactVersionId: result.artifact_version_id,
    version: result.version,
    name: result.name,
    url: result.url,
    expiresAt: result.expires_at,
  }
}

function parseCreatedShare(value: unknown): CreatedShare {
  if (!isRecord(value)
    || typeof value.share_id !== 'string'
    || typeof value.artifact_id !== 'string'
    || typeof value.artifact_version_id !== 'string'
    || typeof value.version !== 'number'
    || !Number.isInteger(value.version)
    || typeof value.name !== 'string'
    || typeof value.source_session_id !== 'string'
    || typeof value.source_path !== 'string'
    || typeof value.mime_type !== 'string'
    || typeof value.size !== 'number'
    || !Number.isFinite(value.size)
    || value.visibility !== 'LINK'
    || value.permission !== 'VIEW_DOWNLOAD'
    || typeof value.created_at !== 'string'
    || (value.expires_at !== null && typeof value.expires_at !== 'string')
    || (value.revoked_at !== null && typeof value.revoked_at !== 'string')
    || (value.url !== null && typeof value.url !== 'string')
    || (value.share_url !== null && typeof value.share_url !== 'string')) {
    throw new ArtifactHubRequestError(502, 'Artifact Hub returned an invalid created Share')
  }
  const share = value as unknown as HubCreatedShare
  return {
    shareId: share.share_id,
    artifactId: share.artifact_id,
    artifactVersionId: share.artifact_version_id,
    version: share.version,
    name: share.name,
    sourceSessionId: share.source_session_id,
    sourcePath: share.source_path,
    mimeType: share.mime_type,
    size: share.size,
    visibility: share.visibility,
    permission: share.permission,
    createdAt: share.created_at,
    expiresAt: share.expires_at,
    revokedAt: share.revoked_at,
    previewUrl: share.url,
    shareUrl: share.share_url,
  }
}

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
