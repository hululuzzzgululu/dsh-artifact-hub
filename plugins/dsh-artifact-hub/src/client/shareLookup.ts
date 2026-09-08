import type { CreatedShare } from '../contracts.ts'

/**
 * Find the creator's current Share for one Session file, if any.
 *
 * Revoked Shares are ignored: their link is dead and a re-share mints a new
 * token, so backfilling their options would mislead. Expired-but-not-revoked
 * Shares are kept — a re-share renews them on the same token.
 */
export function matchCreatedShare(
  shares: readonly CreatedShare[],
  sessionId: string,
  sourcePath: string,
): CreatedShare | null {
  const normalized = normalizeSourcePath(sourcePath)
  const matches = shares.filter(share =>
    share.sourceSessionId === sessionId
    && normalizeSourcePath(share.sourcePath) === normalized
    && share.revokedAt === null)
  if (matches.length === 0) return null
  // One Artifact per (session, path, creator) means at most one live match;
  // picking the highest version is a defensive tie-break.
  return matches.reduce((latest, share) => share.version > latest.version ? share : latest)
}

/**
 * Convert an ISO-8601 timestamp into the local-time `YYYY-MM-DDTHH:mm` value
 * expected by a `datetime-local` input — the reverse of the
 * `new Date(value).toISOString()` round-trip used when submitting.
 */
export function toDatetimeLocalValue(iso: string | null): string {
  if (iso === null) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (value: number): string => String(value).padStart(2, '0')
  return [
    String(date.getFullYear()),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join('-') + 'T' + [
    pad(date.getHours()),
    pad(date.getMinutes()),
  ].join(':')
}

/** Compare source paths across Windows and POSIX separators. */
function normalizeSourcePath(path: string): string {
  return path.replace(/\\/gu, '/')
}
