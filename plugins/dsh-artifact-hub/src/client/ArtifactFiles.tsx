import { useState } from 'react'
import type { CreatedSharesRequester, LocalShareRequester } from './api.ts'
import type { TurnTailOwner } from './deliverables.ts'
import { ShareDialog, type Translate } from './ShareDialog.tsx'

/** Props composed by the DSH turn-tail slot. */
export interface ArtifactFilesProps extends Pick<TurnTailOwner, 'openFile'> {
  readonly matched: readonly string[]
  readonly sessionId: string
  readonly t: Translate
  readonly requestShare: LocalShareRequester
  readonly requestShares: CreatedSharesRequester
  readonly useSessions: <T>(selector: (state: SessionListSnapshot) => T) => T
}

/** Replace the standard produced-file row with open and share actions. */
export function ArtifactFiles({ matched, openFile, sessionId, useSessions, t, requestShare, requestShares }: ArtifactFilesProps) {
  const cwd = useSessions(state => state.byId[sessionId]?.cwd)
  const [sharing, setSharing] = useState<ShareTarget | null>(null)
  return (
    <div style={artifactFilesStyles.root} data-artifact-hub-files>
      <span style={artifactFilesStyles.label}>{t('files.label')}</span>
      <div style={artifactFilesStyles.list}>
        {matched.map((path) => {
          const sourcePath = sessionRelativePath(path, cwd)
          return (
            <div key={path} style={artifactFilesStyles.file} title={path}>
              <button type="button" style={artifactFilesStyles.openButton} onClick={() => { openFile(path) }}>
                <span aria-hidden>▤</span>
                <span style={artifactFilesStyles.name}>{basename(path)}</span>
              </button>
              <button
                type="button"
                style={{ ...artifactFilesStyles.shareButton, ...(sourcePath === null ? artifactFilesStyles.disabled : {}) }}
                disabled={sourcePath === null}
                title={sourcePath === null ? t('files.shareUnavailable') : undefined}
                aria-label={t('files.shareNamed', { name: path })}
                onClick={() => { if (sourcePath !== null) setSharing({ sourcePath }) }}
              >
                {t('files.share')}
              </button>
            </div>
          )
        })}
      </div>
      {sharing !== null && (
        <ShareDialog
          key={sharing.sourcePath}
          sessionId={sessionId}
          sourcePath={sharing.sourcePath}
          t={t}
          requestShare={requestShare}
          requestShares={requestShares}
          onClose={() => { setSharing(null) }}
        />
      )}
    </div>
  )
}

interface SessionListSnapshot {
  readonly byId: Readonly<Record<string, { readonly cwd?: string } | undefined>>
}

interface ShareTarget {
  readonly sourcePath: string
}

/**
 * Convert a DSH file-tool path into the relative source_path expected by Hub.
 * Absolute paths are accepted only when the Session cwd is known and contains
 * the file; parent traversal is never forwarded.
 */
export function sessionRelativePath(path: string, cwd?: string): string | null {
  const normalizedPath = path.replace(/\\/gu, '/')
  const absolute = normalizedPath.startsWith('/') || /^[A-Za-z]:\//u.test(normalizedPath)
  if (!absolute) return cleanRelativePath(normalizedPath)
  if (cwd === undefined) return null
  const normalizedCwd = cwd.replace(/\\/gu, '/').replace(/\/+$/u, '')
  const windows = /^[A-Za-z]:\//u.test(normalizedPath) || /^[A-Za-z]:\//u.test(normalizedCwd)
  const pathForMatch = windows ? normalizedPath.toLowerCase() : normalizedPath
  const cwdForMatch = windows ? normalizedCwd.toLowerCase() : normalizedCwd
  if (pathForMatch === cwdForMatch) return null
  if (!pathForMatch.startsWith(`${cwdForMatch}/`)) return null
  return cleanRelativePath(normalizedPath.slice(normalizedCwd.length + 1))
}

function cleanRelativePath(path: string): string | null {
  const segments = path.split('/').filter(segment => segment !== '' && segment !== '.')
  if (segments.length === 0 || segments.includes('..')) return null
  return segments.join('/')
}

function basename(path: string): string {
  const position = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'))
  return position === -1 ? path : path.slice(position + 1)
}

export const artifactFilesStyles: Record<string, React.CSSProperties> = {
  root: { display: 'flex', alignItems: 'flex-start', gap: 10, marginTop: 10, fontSize: 13 },
  label: { flex: '0 0 auto', paddingTop: 7, color: 'var(--dsw-alias-label-tertiary, #86909c)' },
  list: { display: 'flex', flexWrap: 'wrap', gap: 8, minWidth: 0 },
  file: { display: 'inline-flex', alignItems: 'stretch', maxWidth: 300, border: '1px solid var(--dsw-alias-border-l2, #e5e6eb)', borderRadius: 8, overflow: 'hidden', background: 'var(--dsw-alias-bg-module-platform, #f7f8fa)' },
  openButton: { display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0, border: 0, padding: '6px 9px', background: 'transparent', color: 'var(--dsw-alias-label-primary, #1f2329)', cursor: 'pointer' },
  name: { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  shareButton: { border: 0, borderLeft: '1px solid var(--dsw-alias-border-l2, #e5e6eb)', padding: '6px 9px', background: 'transparent', color: 'var(--dsw-alias-link, #4d6bfe)', cursor: 'pointer' },
  disabled: { cursor: 'not-allowed', opacity: 0.45 },
}
