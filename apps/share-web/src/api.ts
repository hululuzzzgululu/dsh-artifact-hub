import { ShareApiError, type PublicShare, type ShareErrorCode } from './types'

interface ApiEnvelope {
  readonly resultCode?: unknown
  readonly resultMsg?: unknown
  readonly resultObj?: unknown
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export function publicShareUrl(token: string): string {
  return `${apiBaseUrl}/api/public/shares/${encodeURIComponent(token)}`
}

export function contentUrl(token: string): string {
  return `${publicShareUrl(token)}/content`
}

export function downloadUrl(token: string): string {
  return `${publicShareUrl(token)}/download`
}

export async function fetchPublicShare(token: string, signal?: AbortSignal): Promise<PublicShare> {
  let response: Response
  try {
    response = await fetch(publicShareUrl(token), {
      credentials: 'same-origin',
      headers: { accept: 'application/json' },
      signal,
    })
  } catch (reason: unknown) {
    if (reason instanceof DOMException && reason.name === 'AbortError') throw reason
    throw new ShareApiError('network_error', '无法连接到文件分享服务，请稍后重试。')
  }

  const payload = await readEnvelope(response)
  if (!response.ok) {
    const object = isRecord(payload.resultObj) ? payload.resultObj : null
    const code = normalizeErrorCode(object?.code)
    const message = typeof payload.resultMsg === 'string' ? payload.resultMsg : '分享访问失败'
    throw new ShareApiError(code, message, response.status)
  }
  if (!isRecord(payload.resultObj)) {
    throw new ShareApiError('invalid_response', '文件分享服务返回了无效数据。', response.status)
  }
  return parsePublicShare(payload.resultObj, response.status)
}

async function readEnvelope(response: Response): Promise<ApiEnvelope> {
  try {
    const value: unknown = await response.json()
    return isRecord(value) ? value : {}
  } catch {
    throw new ShareApiError('invalid_response', '文件分享服务返回了无法解析的数据。', response.status)
  }
}

function parsePublicShare(value: Readonly<Record<string, unknown>>, status: number): PublicShare {
  if (
    typeof value.name !== 'string'
    || typeof value.mime_type !== 'string'
    || typeof value.size !== 'number'
    || typeof value.version !== 'number'
    || value.visibility !== 'LINK'
    || value.permission !== 'VIEW_DOWNLOAD'
    || typeof value.created_by_id !== 'string'
    || typeof value.created_by_name !== 'string'
    || typeof value.created_at !== 'string'
    || (value.expires_at !== null && typeof value.expires_at !== 'string')
  ) {
    throw new ShareApiError('invalid_response', '文件分享服务返回了不完整的分享信息。', status)
  }
  return {
    name: value.name,
    mimeType: value.mime_type,
    size: value.size,
    version: value.version,
    visibility: value.visibility,
    permission: value.permission,
    createdById: value.created_by_id,
    createdByName: value.created_by_name,
    createdAt: value.created_at,
    expiresAt: value.expires_at,
  }
}

function normalizeErrorCode(value: unknown): ShareErrorCode {
  const known = new Set<ShareErrorCode>([
    'share_expired',
    'share_revoked',
    'access_restricted',
    'not_found',
  ])
  return typeof value === 'string' && known.has(value as ShareErrorCode)
    ? value as ShareErrorCode
    : 'unknown'
}

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
