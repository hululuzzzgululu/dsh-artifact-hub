import { useEffect, useMemo, useState } from 'react'
import type {
  WorkspaceFileEntry,
  WorkspaceFilesResult,
} from '../contracts.ts'
import type {
  CreatedSharesRequester,
  LocalShareRequester,
  WorkspaceFilesRequester,
} from './api.ts'
import { sessionRelativePath } from './ArtifactFiles.tsx'
import { ShareDialog } from './ShareDialog.tsx'
import type { ArtifactHubKey, ArtifactHubTranslate } from './locales.ts'

/** Minimal Chat snapshot face needed to associate an assistant message with its Turn. */
export interface ChatSnapshotLike {
  readonly nodes: {
    readonly values: () => readonly ChatNodeLike[]
  }
}

/**
 * The current DSH conversation runtime exposes the chat target through the
 * session snapshot. Keeping this small adapter local lets the action remain
 * compatible with the older `useSession` slot contract without coupling the
 * plugin build to DSH's private runtime package.
 */
export interface SessionSnapshotLike {
  readonly chat: ChatSnapshotLike
}

interface ChatNodeLike {
  readonly data: unknown
  readonly location: unknown
}

interface TurnLike {
  readonly data: {
    readonly get: (key: string) => unknown
  }
}

interface MessageTurn {
  readonly turn: TurnLike
  readonly seq: number
}

/** Full props of the message action injected into the Chat assistant-actions row. */
export interface ArtifactShareActionProps {
  readonly messageId: string
  readonly sessionId: string
  readonly useSession: <T>(selector: (snapshot: SessionSnapshotLike) => T) => T
  readonly useSessions: <T>(selector: (snapshot: SessionListSnapshot) => T) => T
  readonly t: ArtifactHubTranslate
  readonly requestShare: LocalShareRequester
  readonly requestShares: CreatedSharesRequester
  readonly requestWorkspaceFiles: WorkspaceFilesRequester
}

/** Resolve the Turn containing one finalized assistant message. */
export function findTurnForMessage(snapshot: ChatSnapshotLike, messageId: string): MessageTurn | undefined {
  for (const node of snapshot.nodes.values()) {
    const data = asRecord(node.data)
    const finalNode = asRecord(data?.finalNode)
    if (finalNode?.messageId !== messageId) continue
    const seq = finalNode.seq
    if (typeof seq !== 'number' || !Number.isFinite(seq)) return undefined
    const location = asRecord(node.location)
    const turn = location?.kind === 'turn'
      ? location.turn
      : location?.kind === 'step'
        ? asRecord(location.turn)
        : undefined
    if (!isTurnLike(turn)) return undefined
    return { turn, seq }
  }
  return undefined
}

/** Read this message's successful produced paths, preserving first-seen order. */
export function producedPathsForMessage(snapshot: ChatSnapshotLike, messageId: string): readonly string[] {
  const match = findTurnForMessage(snapshot, messageId)
  if (match === undefined) return []
  const data = asRecord(match.turn.data.get('deliverables'))
  const produced = data?.produced
  if (!Array.isArray(produced)) return []
  const paths: string[] = []
  const seen = new Set<string>()
  for (const item of produced) {
    const record = asRecord(item)
    if (record === undefined
      || typeof record.seq !== 'number'
      || !Number.isFinite(record.seq)
      || record.seq > match.seq
      || typeof record.path !== 'string'
      || record.path.trim() === ''
      || seen.has(record.path)) continue
    seen.add(record.path)
    paths.push(record.path)
  }
  return paths
}

/** Share action shown in every finalized Assistant message's bottom action row. */
export function ArtifactShareAction({
  messageId,
  sessionId,
  useSession,
  t,
  requestShare,
  requestShares,
  requestWorkspaceFiles,
  useSessions,
}: ArtifactShareActionProps): JSX.Element {
  const cwd = useSessions(state => state.byId[sessionId]?.cwd)
  const producedPaths = useSession(snapshot => producedPathsForMessage(snapshot.chat, messageId))
    .map(path => sessionRelativePath(path, cwd))
    .filter((path): path is string => path !== null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const shareDialogTranslate = (key: string, parameters?: Readonly<Record<string, string>>): string =>
    t(key as ArtifactHubKey, parameters)

  const shareButton = (
    <button
      type="button"
      aria-label={t('action.shareFiles')}
      title={t('action.shareFiles')}
      style={styles.action}
      onClick={() => { setPickerOpen(true) }}
    >
      <FileShareIcon />
    </button>
  )
  return (
    <>
      {shareButton}
      {pickerOpen && (
        <WorkspaceFilePicker
          sessionId={sessionId}
          producedPaths={producedPaths}
          requestWorkspaceFiles={requestWorkspaceFiles}
          t={t}
          onSelect={(path) => {
            setPickerOpen(false)
            setSelectedPath(path)
          }}
          onClose={() => { setPickerOpen(false) }}
        />
      )}
      {selectedPath !== null && (
        <ShareDialog
          sessionId={sessionId}
          sourcePath={selectedPath}
          t={shareDialogTranslate}
          requestShare={requestShare}
          requestShares={requestShares}
          onClose={() => { setSelectedPath(null) }}
        />
      )}
    </>
  )
}

interface WorkspaceFilePickerProps {
  readonly sessionId: string
  readonly producedPaths: readonly string[]
  readonly requestWorkspaceFiles: WorkspaceFilesRequester
  readonly t: ArtifactHubTranslate
  readonly onSelect: (path: string) => void
  readonly onClose: () => void
}

interface SessionListSnapshot {
  readonly byId: Readonly<Record<string, { readonly cwd?: string } | undefined>>
}

function WorkspaceFilePicker({
  sessionId,
  producedPaths,
  requestWorkspaceFiles,
  t,
  onSelect,
  onClose,
}: WorkspaceFilePickerProps): JSX.Element {
  const [directory, setDirectory] = useState('')
  const [listing, setListing] = useState<WorkspaceFilesResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')

  useEffect(() => {
    const abort = new AbortController()
    setLoading(true)
    setError('')
    void requestWorkspaceFiles({ sessionId, directory }, abort.signal)
      .then(value => {
        if (!abort.signal.aborted) setListing(value)
      })
      .catch(() => {
        if (!abort.signal.aborted) {
          setListing(null)
          setError(t('picker.error'))
        }
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false)
      })
    return () => { abort.abort() }
  }, [directory, requestWorkspaceFiles, sessionId])

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => { document.removeEventListener('keydown', closeOnEscape) }
  }, [onClose])

  const produced = useMemo(
    () => producedPaths.map(path => ({
      name: basename(path),
      path,
      kind: 'file' as const,
    })),
    [producedPaths],
  )
  const normalizedQuery = query.trim().toLocaleLowerCase()
  const producedSet = useMemo(() => new Set(producedPaths), [producedPaths])
  const entries = (listing?.entries ?? []).filter(entry =>
    !producedSet.has(entry.path)
      && (normalizedQuery === ''
      || entry.name.toLocaleLowerCase().includes(normalizedQuery)
      || entry.path.toLocaleLowerCase().includes(normalizedQuery)))
  const parent = parentDirectory(directory)

  return (
    <div style={styles.backdrop} role="presentation" onMouseDown={event => {
      if (event.currentTarget === event.target) onClose()
    }}>
      <section style={styles.dialog} role="dialog" aria-modal="true" aria-labelledby="artifact-share-picker-title">
        <header style={styles.header}>
          <div>
            <h2 id="artifact-share-picker-title" style={styles.title}>{t('picker.title')}</h2>
            <div style={styles.path}>{directory === '' ? '/' : `/${directory}`}</div>
          </div>
          <button type="button" style={styles.close} aria-label={t('picker.close')} onClick={onClose}>×</button>
        </header>
        <div style={styles.body}>
          {produced.length > 0 && (
            <section style={styles.section} aria-label={t('picker.produced')}>
              <h3 style={styles.sectionTitle}>{t('picker.produced')}</h3>
              <div style={styles.entries}>
                {produced.map(entry => <FileEntry key={`produced:${entry.path}`} entry={entry} onSelect={onSelect} />)}
              </div>
            </section>
          )}
          <section style={styles.section} aria-label={t('picker.workspace')}>
            <div style={styles.sectionHeader}>
              <h3 style={styles.sectionTitle}>{t('picker.workspace')}</h3>
              <input
                type="search"
                value={query}
                style={styles.search}
                aria-label={t('picker.search')}
                placeholder={t('picker.search')}
                onChange={event => { setQuery(event.currentTarget.value) }}
              />
            </div>
            {directory !== '' && (
              <button type="button" style={styles.parent} onClick={() => { setDirectory(parent) }}>
                ← {t('picker.up')}
              </button>
            )}
            {loading && <div style={styles.state}>{t('picker.loading')}</div>}
            {error !== '' && <div style={styles.error} role="alert">{error}</div>}
            {!loading && error === '' && entries.length === 0 && <div style={styles.state}>{t('picker.empty')}</div>}
            {!loading && error === '' && entries.length > 0 && (
              <div style={styles.entries}>
                {entries.map(entry => <FileEntry key={entry.path} entry={entry} onSelect={onSelect} onOpenDirectory={setDirectory} />)}
              </div>
            )}
            {listing?.truncated === true && <div style={styles.hint}>{t('picker.truncated')}</div>}
          </section>
        </div>
      </section>
    </div>
  )
}

function FileEntry({
  entry,
  onSelect,
  onOpenDirectory,
}: {
  readonly entry: WorkspaceFileEntry
  readonly onSelect: (path: string) => void
  readonly onOpenDirectory?: (path: string) => void
}): JSX.Element {
  if (entry.kind === 'directory') {
    return (
      <button type="button" style={styles.entry} onClick={() => { onOpenDirectory?.(entry.path) }}>
        <span aria-hidden>▰</span><span style={styles.entryName}>{entry.name}</span><span aria-hidden>›</span>
      </button>
    )
  }
  return (
    <button type="button" style={styles.entry} onClick={() => { onSelect(entry.path) }}>
      <span aria-hidden>▤</span><span style={styles.entryName}>{entry.name}</span>
      {entry.size === undefined ? null : <span style={styles.entryMeta}>{formatBytes(entry.size)}</span>}
    </button>
  )
}

function isTurnLike(value: unknown): value is TurnLike {
  const record = asRecord(value)
  const data = asRecord(record?.data)
  return typeof data?.get === 'function'
}

function asRecord(value: unknown): Readonly<Record<string, unknown>> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Readonly<Record<string, unknown>>
    : undefined
}

function basename(path: string): string {
  const position = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'))
  return position === -1 ? path : path.slice(position + 1)
}

function parentDirectory(directory: string): string {
  const position = directory.lastIndexOf('/')
  return position === -1 ? '' : directory.slice(0, position)
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${String(bytes)} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function FileShareIcon(): JSX.Element {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 3h8l6 6v12H5z" />
      <path d="M13 3v6h6" />
      <path d="M8.5 16h7" />
      <path d="m12.5 13 3 3-3 3" />
    </svg>
  )
}

const styles: Record<string, React.CSSProperties> = {
  action: { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 3, width: 'calc(28px + var(--dsh-content-font-delta, 0px))', height: 'calc(28px + var(--dsh-content-font-delta, 0px))', boxSizing: 'border-box', border: 0, borderRadius: 28, padding: 4, background: 'transparent', color: 'var(--dsw-alias-label-tertiary, #86909c)', cursor: 'pointer' },
  backdrop: { position: 'fixed', inset: 0, zIndex: 1000, display: 'grid', placeItems: 'center', padding: 20, background: 'rgba(31, 35, 41, .22)' },
  dialog: { display: 'flex', flexDirection: 'column', width: 'min(560px, 100%)', maxHeight: 'min(600px, 80vh)', overflow: 'hidden', border: '1px solid var(--dsw-alias-border-l2, #e5e6eb)', borderRadius: 12, background: 'var(--dsw-alias-bg-base, #fff)', color: 'var(--dsw-alias-label-primary, #1f2329)', boxShadow: '0 16px 48px rgba(31, 35, 41, .18)' },
  header: { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, padding: '18px 20px', borderBottom: '1px solid var(--dsw-alias-border-l2, #e5e6eb)' },
  title: { margin: 0, fontSize: 17, lineHeight: 1.35, fontWeight: 650 },
  path: { marginTop: 4, color: 'var(--dsw-alias-label-tertiary, #86909c)', fontSize: 12 },
  close: { border: 0, padding: '0 4px', background: 'transparent', color: 'var(--dsw-alias-label-tertiary, #86909c)', fontSize: 24, lineHeight: 1, cursor: 'pointer' },
  body: { overflow: 'auto', padding: 18 },
  section: { display: 'grid', gap: 8, marginBottom: 18 },
  sectionHeader: { display: 'flex', alignItems: 'center', gap: 8 },
  sectionTitle: { flex: '1 1 auto', margin: 0, fontSize: 12, color: 'var(--dsw-alias-label-secondary, #646a73)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.04em' },
  search: { width: 180, maxWidth: '45%', height: 30, boxSizing: 'border-box', border: '1px solid var(--dsw-alias-border-l2, #e5e6eb)', borderRadius: 7, padding: '0 9px', background: 'var(--dsw-alias-bg-layer-1, #fff)', color: 'inherit', font: 'inherit', fontSize: 12 },
  entries: { display: 'grid', gap: 3 },
  entry: { display: 'flex', alignItems: 'center', gap: 9, width: '100%', minHeight: 36, border: 0, borderRadius: 7, padding: '6px 9px', background: 'var(--dsw-alias-bg-module-platform, #f7f8fa)', color: 'inherit', font: 'inherit', fontSize: 13, textAlign: 'left', cursor: 'pointer' },
  entryName: { flex: '1 1 auto', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  entryMeta: { flex: '0 0 auto', color: 'var(--dsw-alias-label-tertiary, #86909c)', fontSize: 11 },
  parent: { justifySelf: 'start', border: 0, padding: '3px 0', background: 'transparent', color: 'var(--dsw-alias-link, #4d6bfe)', font: 'inherit', fontSize: 12, cursor: 'pointer' },
  state: { padding: 18, color: 'var(--dsw-alias-label-tertiary, #86909c)', fontSize: 13, textAlign: 'center' },
  error: { borderRadius: 7, padding: '8px 10px', color: 'var(--dsw-alias-state-error-primary, #e34d59)', background: 'var(--dsw-alias-state-error-bg, rgba(227,77,89,.08))', fontSize: 12 },
  hint: { color: 'var(--dsw-alias-label-tertiary, #86909c)', fontSize: 11 },
}
