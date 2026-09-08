export interface PublicShare {
  readonly name: string
  readonly mimeType: string
  readonly size: number
  readonly version: number
  readonly visibility: 'LINK'
  readonly permission: 'VIEW_DOWNLOAD'
  readonly createdById: string
  readonly createdByName: string
  readonly createdAt: string
  readonly expiresAt: string | null
}

export type ShareErrorCode =
  | 'share_expired'
  | 'share_revoked'
  | 'access_restricted'
  | 'not_found'
  | 'invalid_response'
  | 'network_error'
  | 'unknown'

export class ShareApiError extends Error {
  readonly code: ShareErrorCode
  readonly status: number | null

  constructor(code: ShareErrorCode, message: string, status: number | null = null) {
    super(message)
    this.name = 'ShareApiError'
    this.code = code
    this.status = status
  }
}
