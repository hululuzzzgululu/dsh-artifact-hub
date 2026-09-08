/** Logical DSH Connection RPC target used by the browser plugin. */
export const LOCAL_SHARE_RPC_CHANNEL = '/artifact-hub'
export const LOCAL_SHARE_RPC_ENDPOINT = 'shares'
export const CREATED_SHARES_RPC_ENDPOINT = 'created-shares'

/** Browser-to-Host request for one Local snapshot. */
export interface LocalShareRequest {
  readonly sessionId: string
  readonly sourcePath: string
  readonly expiresAt?: string
  readonly artifactId?: string
}

/** Browser-safe subset of the Hub creation result. */
export interface LocalShareResult {
  readonly shareId: string
  readonly artifactId: string
  readonly artifactVersionId: string
  readonly version: number
  readonly name: string
  readonly url: string
  readonly expiresAt: string | null
}

/** Browser-safe metadata for a Share created by the signed-in DSH identity. */
export interface CreatedShare {
  readonly shareId: string
  readonly artifactId: string
  readonly artifactVersionId: string
  readonly version: number
  readonly name: string
  readonly sourceSessionId: string
  readonly sourcePath: string
  readonly mimeType: string
  readonly size: number
  readonly visibility: 'LINK'
  readonly permission: 'VIEW_DOWNLOAD'
  readonly createdAt: string
  readonly expiresAt: string | null
  readonly revokedAt: string | null
  /** Short-lived owner preview URL. Null when the Share is no longer active. */
  readonly previewUrl: string | null
  /** Durable owner share URL rebuilt from the stored token. Null for revoked
   * shares and legacy rows migrated before the token was persisted. */
  readonly shareUrl: string | null
}

/** DSH's business-result envelope, narrowed to what this plugin consumes. */
export type LocalShareRpcResult<T> = {
  readonly ok: true
  readonly value: T
} | {
  readonly ok: false
  readonly error: {
    readonly code: string
    readonly message: string
    readonly details: Readonly<Record<string, unknown>>
  }
}
