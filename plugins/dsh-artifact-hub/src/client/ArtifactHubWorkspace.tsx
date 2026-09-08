import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import type { CreatedShare } from '../contracts.ts'
import type { ArtifactHubTranslate } from './locales.ts'
import type { ArtifactHubWorkspaceController } from './workspace-controller.ts'

interface Bounds {
  readonly left: number
  readonly top: number
  readonly width: number
  readonly height: number
}

export interface ArtifactHubWorkspaceProps {
  readonly controller: ArtifactHubWorkspaceController
  readonly requestShares: (signal?: AbortSignal) => Promise<readonly CreatedShare[]>
  readonly t: ArtifactHubTranslate
}

export type ShareStatus = 'active' | 'expired' | 'revoked'
export type ShareStatusFilter = 'all' | ShareStatus

const COLLAPSED_VERSION_COUNT = 3

export interface ArtifactShareGroup {
  readonly artifactId: string
  readonly name: string
  readonly mimeType: string
  readonly shares: readonly CreatedShare[]
}

function resolveSurface(): HTMLElement | undefined {
  return document.querySelector<HTMLElement>('[data-pane="conversation"]')
    ?? document.querySelector<HTMLElement>('.dshDesktopConversationSurface')
    ?? document.querySelector<HTMLElement>('[class*="centerCol"]')
    ?? undefined
}

/** Share management surface opened from the persistent left navigation. */
export function ArtifactHubWorkspace({ controller, requestShares, t }: ArtifactHubWorkspaceProps): JSX.Element | null {
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot)
  const [bounds, setBounds] = useState<Bounds>()
  const [shares, setShares] = useState<readonly CreatedShare[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<ShareStatusFilter>('all')

  const load = useCallback(async (signal?: AbortSignal): Promise<void> => {
    setLoading(true)
    setError('')
    try {
      setShares(await requestShares(signal))
    } catch (reason: unknown) {
      if (signal?.aborted === true) return
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      if (signal?.aborted !== true) setLoading(false)
    }
  }, [requestShares])

  useEffect(() => {
    if (!state.open) return
    const abort = new AbortController()
    void load(abort.signal)
    return () => { abort.abort() }
  }, [load, state.open])

  useEffect(() => {
    if (!state.open) return
    let surface: HTMLElement | undefined
    const update = (): void => {
      surface = resolveSurface()
      if (surface === undefined) return
      const rect = surface.getBoundingClientRect()
      setBounds(previous => previous?.left === rect.left
        && previous.top === rect.top
        && previous.width === rect.width
        && previous.height === rect.height
        ? previous
        : { left: rect.left, top: rect.top, width: rect.width, height: rect.height })
    }
    update()
    const resize = typeof ResizeObserver === 'undefined' ? undefined : new ResizeObserver(update)
    if (surface !== undefined) resize?.observe(surface)
    const shell = new MutationObserver(update)
    shell.observe(document.body, { childList: true, subtree: true })
    window.addEventListener('resize', update)
    const escape = (event: KeyboardEvent): void => {
      if (event.key === 'Escape' && !event.defaultPrevented) controller.close()
    }
    window.addEventListener('keydown', escape)
    return () => {
      resize?.disconnect()
      shell.disconnect()
      window.removeEventListener('resize', update)
      window.removeEventListener('keydown', escape)
    }
  }, [controller, state.open])

  const groups = useMemo(
    () => filterArtifactGroups(groupCreatedShares(shares), query, statusFilter),
    [query, shares, statusFilter],
  )
  const visibleShares = groups.reduce((count, group) => count + group.shares.length, 0)

  if (!state.open || bounds === undefined) return null
  return (
    <section
      data-artifact-hub-workspace
      aria-label={t('center.label')}
      style={{ ...styles.panel, ...bounds }}
    >
      <header style={styles.header}>
        <h1 style={styles.title}>{t('center.label')}</h1>
        <p style={styles.subtitle}>{t('center.subtitle')}</p>
      </header>
      <main style={styles.body}>
        <div style={styles.content}>
          <div style={styles.toolbar}>
            <label style={styles.search}>
              <SearchIcon />
              <span style={styles.visuallyHidden}>{t('center.searchLabel')}</span>
              <input
                type="search"
                value={query}
                style={styles.searchInput}
                placeholder={t('center.searchPlaceholder')}
                onChange={event => { setQuery(event.currentTarget.value) }}
              />
            </label>
            <label style={styles.filterLabel}>
              <span style={styles.visuallyHidden}>{t('center.statusFilter')}</span>
              <select
                value={statusFilter}
                style={styles.select}
                aria-label={t('center.statusFilter')}
                onChange={event => { setStatusFilter(event.currentTarget.value as ShareStatusFilter) }}
              >
                <option value="all">{t('center.filterAll')}</option>
                <option value="active">{t('center.active')}</option>
                <option value="expired">{t('center.expired')}</option>
                <option value="revoked">{t('center.revoked')}</option>
              </select>
            </label>
            <button
              type="button"
              style={{ ...styles.iconButton, ...(loading ? styles.disabled : {}) }}
              disabled={loading}
              aria-label={t('center.refresh')}
              title={t('center.refresh')}
              onClick={() => { void load() }}
            >
              <RefreshIcon />
            </button>
          </div>

          {shares.length > 0 && (
            <div style={styles.resultSummary} aria-live="polite">
              {t('center.results', {
                files: String(groups.length),
                shares: String(visibleShares),
              })}
            </div>
          )}

          {loading && shares.length === 0
            ? <div style={styles.state}>{t('center.loading')}</div>
            : error !== '' && shares.length === 0
              ? <div style={styles.error} role="alert"><strong>{t('center.error')}</strong><span>{error}</span></div>
              : shares.length === 0
                ? <div style={styles.state}>{t('center.empty')}</div>
                : groups.length === 0
                  ? <div style={styles.state}>{t('center.noResults')}</div>
                  : (
                    <div style={styles.list}>
                      {error !== '' && <div style={styles.inlineError} role="alert">{t('center.error')}: {error}</div>}
                      {groups.map(group => <ArtifactCard key={group.artifactId} group={group} t={t} />)}
                    </div>
                  )}
        </div>
      </main>
    </section>
  )
}

function ArtifactCard({ group, t }: { readonly group: ArtifactShareGroup; readonly t: ArtifactHubTranslate }): JSX.Element {
  const [versionsExpanded, setVersionsExpanded] = useState(false)
  const latestVersion = Math.max(...group.shares.map(share => share.version))
  const latestShare = group.shares.find(share => share.version === latestVersion) ?? group.shares[0]!
  const previewShare = [...group.shares]
    .filter(share => statusOf(share) === 'active' && share.previewUrl !== null)
    .sort((left, right) => right.version - left.version || compareShares(left, right))[0]
  const versionShares = selectVisibleVersionShares(group.shares, versionsExpanded)
  const hiddenVersionCount = group.shares.length - versionShares.length
  const name = previewShare === undefined
    ? <strong style={styles.name} title={group.name}>{group.name}</strong>
    : (
      <a
        style={styles.nameLink}
        href={previewShare.previewUrl ?? undefined}
        target="_blank"
        rel="noreferrer"
        title={t('center.previewNamed', { name: group.name })}
      >
        {group.name}
      </a>
    )

  return (
    <article style={styles.card}>
      <div style={styles.artifactHeader}>
        <div style={styles.fileIcon} aria-hidden>▤</div>
        <div style={styles.artifactSummary}>
          <div style={styles.nameRow}>
            {name}
          </div>
          <div style={styles.meta}>
            <span>{t('center.latestVersion', { version: String(latestVersion) })}</span>
            <span>{formatBytes(latestShare.size)}</span>
            <span>{t('center.shareCount', { count: String(group.shares.length) })}</span>
            <span>{t('center.recent', { time: formatDate(group.shares[0]!.createdAt) })}</span>
          </div>
        </div>
        {previewShare !== undefined && (
          <a
            style={styles.primaryAction}
            href={previewShare.previewUrl ?? undefined}
            target="_blank"
            rel="noreferrer"
          >
            {t('center.preview')} <span aria-hidden>↗</span>
          </a>
        )}
      </div>

      <div style={styles.versions}>
        {versionShares.map(share => (
          <section key={share.artifactVersionId} style={styles.versionGroup} aria-label={t('center.version', { version: String(share.version) })}>
            <div style={styles.versionHeader}>
              <strong>{t('center.versionShort', { version: String(share.version) })}</strong>
              <span>{formatBytes(share.size)}</span>
            </div>
            <div style={styles.shareRows}>
              <ShareRow share={share} t={t} />
            </div>
          </section>
        ))}
        {group.shares.length > COLLAPSED_VERSION_COUNT && (
          <button
            type="button"
            style={styles.versionToggle}
            aria-expanded={versionsExpanded}
            onClick={() => { setVersionsExpanded(expanded => !expanded) }}
          >
            {versionsExpanded
              ? t('center.collapseVersions')
              : t('center.expandVersions', { count: String(hiddenVersionCount) })}
            <span aria-hidden>{versionsExpanded ? ' ↑' : ' ↓'}</span>
          </button>
        )}
      </div>
    </article>
  )
}

function ShareRow({ share, t }: { readonly share: CreatedShare; readonly t: ArtifactHubTranslate }): JSX.Element {
  const status = statusOf(share)
  return (
    <div style={styles.shareRow}>
      <span style={{ ...styles.status, ...statusStyles[status] }}>{t(`center.${status}`)}</span>
      <span style={styles.shareTime}>{t('center.created', { time: formatDate(share.createdAt) })}</span>
      <span style={styles.shareExpiry}>
        {share.expiresAt === null
          ? t('center.noExpiry')
          : t('center.expires', { time: formatDate(share.expiresAt) })}
      </span>
      {status === 'active' && share.previewUrl !== null
        ? (
          <a style={styles.rowAction} href={share.previewUrl} target="_blank" rel="noreferrer">
            {t('center.preview')} <span aria-hidden>↗</span>
          </a>
        )
        : <span style={styles.unavailable}>{t('center.previewUnavailable')}</span>}
    </div>
  )
}

/** Sort versions newest-first and limit a collapsed Artifact card to three rows. */
export function selectVisibleVersionShares(
  shares: readonly CreatedShare[],
  expanded: boolean,
): readonly CreatedShare[] {
  const sorted = [...shares].sort((left, right) => right.version - left.version)
  return expanded ? sorted : sorted.slice(0, COLLAPSED_VERSION_COUNT)
}

/** Group creator-list records by stable Artifact identity, never by display name. */
export function groupCreatedShares(shares: readonly CreatedShare[]): readonly ArtifactShareGroup[] {
  const groups = new Map<string, CreatedShare[]>()
  for (const share of shares) {
    const group = groups.get(share.artifactId)
    if (group === undefined) groups.set(share.artifactId, [share])
    else group.push(share)
  }
  return [...groups.entries()].map(([artifactId, artifactShares]) => {
    const sorted = [...artifactShares].sort(compareShares)
    return {
      artifactId,
      name: sorted[0]!.name,
      mimeType: sorted[0]!.mimeType,
      shares: sorted,
    }
  }).sort((left, right) => compareShares(left.shares[0]!, right.shares[0]!))
}

/** Apply status first, then retain matching Share records inside matching Artifacts. */
export function filterArtifactGroups(
  groups: readonly ArtifactShareGroup[],
  query: string,
  status: ShareStatusFilter,
): readonly ArtifactShareGroup[] {
  const normalized = query.trim().toLocaleLowerCase()
  return groups.flatMap(group => {
    const artifactMatches = normalized === '' || [group.name, group.mimeType, group.artifactId]
      .some(value => value.toLocaleLowerCase().includes(normalized))
    const shares = group.shares.filter(share => {
      if (status !== 'all' && statusOf(share) !== status) return false
      return artifactMatches || [share.shareId, `v${String(share.version)}`, String(share.version)]
        .some(value => value.toLocaleLowerCase().includes(normalized))
    })
    return shares.length === 0 ? [] : [{ ...group, shares }]
  })
}

export function statusOf(share: CreatedShare): ShareStatus {
  if (share.revokedAt !== null) return 'revoked'
  if (share.expiresAt !== null && Date.parse(share.expiresAt) <= Date.now()) return 'expired'
  return 'active'
}

function compareShares(left: CreatedShare, right: CreatedShare): number {
  return Date.parse(right.createdAt) - Date.parse(left.createdAt)
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${String(bytes)} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleString([], {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
}

function SearchIcon(): JSX.Element {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
    </svg>
  )
}

function RefreshIcon(): JSX.Element {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 11a8 8 0 1 0-2.34 5.66" />
      <path d="M20 5v6h-6" />
    </svg>
  )
}

export const artifactHubWorkspaceStyles = {
  panel: { boxSizing: 'border-box', position: 'fixed', zIndex: 20, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, overflow: 'hidden', pointerEvents: 'auto', background: 'var(--dsw-alias-bg-base, #fff)', color: 'var(--dsw-alias-label-primary, #1f2329)' },
  header: { flex: '0 0 auto', padding: '28px 36px 22px', borderBottom: '1px solid var(--dsw-alias-border-l2, #e5e6eb)' },
  title: { margin: 0, fontSize: 24, lineHeight: 1.3, fontWeight: 650 },
  subtitle: { margin: '7px 0 0', color: 'var(--dsw-alias-label-secondary, #646a73)', fontSize: 13, lineHeight: 1.5 },
  body: { flex: '1 1 auto', minHeight: 0, overflow: 'auto', padding: '24px 36px 48px' },
  content: { width: '100%', maxWidth: 1040, margin: '0 auto' },
  toolbar: { display: 'flex', alignItems: 'center', gap: 10 },
  search: { flex: '1 1 auto', display: 'flex', alignItems: 'center', gap: 9, minWidth: 160, maxWidth: 560, height: 38, boxSizing: 'border-box', border: '1px solid var(--dsw-alias-border-l2, #e5e6eb)', borderRadius: 9, padding: '0 11px', background: 'var(--dsw-alias-bg-layer-1, #fff)', color: 'var(--dsw-alias-label-tertiary, #86909c)' },
  searchInput: { flex: '1 1 auto', minWidth: 0, height: '100%', border: 0, outline: 0, padding: 0, background: 'transparent', color: 'var(--dsw-alias-label-primary, #1f2329)', font: 'inherit', fontSize: 13 },
  filterLabel: { flex: '0 0 auto' },
  select: { height: 38, boxSizing: 'border-box', border: '1px solid var(--dsw-alias-border-l2, #e5e6eb)', borderRadius: 9, padding: '0 30px 0 11px', background: 'var(--dsw-alias-bg-layer-1, #fff)', color: 'inherit', font: 'inherit', fontSize: 13, cursor: 'pointer' },
  iconButton: { flex: '0 0 auto', display: 'grid', placeItems: 'center', width: 38, height: 38, border: '1px solid var(--dsw-alias-border-l2, #e5e6eb)', borderRadius: 9, padding: 0, background: 'var(--dsw-alias-bg-layer-1, #fff)', color: 'var(--dsw-alias-label-secondary, #646a73)', cursor: 'pointer' },
  disabled: { cursor: 'wait', opacity: 0.5 },
  visuallyHidden: { position: 'absolute', width: 1, height: 1, padding: 0, margin: -1, overflow: 'hidden', clip: 'rect(0, 0, 0, 0)', whiteSpace: 'nowrap', border: 0 },
  resultSummary: { margin: '14px 2px 10px', color: 'var(--dsw-alias-label-tertiary, #86909c)', fontSize: 12 },
  list: { display: 'grid', gap: 14 },
  card: { overflow: 'hidden', border: '1px solid var(--dsw-alias-border-l2, #e5e6eb)', borderRadius: 12, background: 'var(--dsw-alias-bg-layer-1, #fff)' },
  artifactHeader: { display: 'flex', alignItems: 'center', gap: 14, padding: '17px 18px' },
  fileIcon: { flex: '0 0 auto', display: 'grid', placeItems: 'center', width: 40, height: 40, borderRadius: 9, background: 'var(--dsw-alias-bg-module-platform, #f7f8fa)', color: 'var(--dsw-alias-label-secondary, #646a73)', fontSize: 18 },
  artifactSummary: { flex: '1 1 auto', minWidth: 0, display: 'grid', gap: 7 },
  nameRow: { display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 },
  name: { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 15 },
  nameLink: { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--dsw-alias-label-primary, #1f2329)', fontSize: 15, fontWeight: 650, textDecoration: 'none' },
  status: { flex: '0 0 auto', borderRadius: 999, padding: '2px 8px', fontSize: 12, lineHeight: 1.5 },
  meta: { display: 'flex', flexWrap: 'wrap', gap: '5px 14px', color: 'var(--dsw-alias-label-secondary, #646a73)', fontSize: 12 },
  primaryAction: { flex: '0 0 auto', border: '1px solid var(--dsw-alias-border-l2, #e5e6eb)', borderRadius: 8, padding: '7px 11px', color: 'var(--dsw-alias-link, #4d6bfe)', fontSize: 13, fontWeight: 500, textDecoration: 'none' },
  versions: { borderTop: '1px solid var(--dsw-alias-border-l3, #f0f1f2)', background: 'var(--dsw-alias-bg-module-platform, #f7f8fa)' },
  versionGroup: { display: 'grid', gridTemplateColumns: '96px minmax(0, 1fr)', borderBottom: '1px solid var(--dsw-alias-border-l3, #f0f1f2)' },
  versionHeader: { display: 'flex', flexDirection: 'column', gap: 5, padding: '13px 16px 13px 18px', color: 'var(--dsw-alias-label-secondary, #646a73)', fontSize: 12 },
  shareRows: { minWidth: 0, background: 'var(--dsw-alias-bg-layer-1, #fff)' },
  shareRow: { display: 'grid', gridTemplateColumns: 'auto minmax(150px, 1fr) minmax(150px, 1fr) auto', alignItems: 'center', gap: 12, minHeight: 48, boxSizing: 'border-box', padding: '8px 14px', fontSize: 12 },
  versionToggle: { display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', border: 0, padding: '10px 16px', background: 'var(--dsw-alias-bg-layer-1, #fff)', color: 'var(--dsw-alias-link, #4d6bfe)', font: 'inherit', fontSize: 12, cursor: 'pointer' },
  shareTime: { minWidth: 0, color: 'var(--dsw-alias-label-secondary, #646a73)' },
  shareExpiry: { minWidth: 0, color: 'var(--dsw-alias-label-tertiary, #86909c)' },
  rowAction: { color: 'var(--dsw-alias-link, #4d6bfe)', fontWeight: 500, textDecoration: 'none', whiteSpace: 'nowrap' },
  unavailable: { color: 'var(--dsw-alias-label-disabled, #c9cdd4)', whiteSpace: 'nowrap' },
  state: { display: 'grid', minHeight: 240, placeItems: 'center', color: 'var(--dsw-alias-label-tertiary, #86909c)', textAlign: 'center' },
  error: { display: 'grid', gap: 8, maxWidth: 560, margin: '80px auto', border: '1px solid var(--dsw-alias-state-error-border, #f5c2c7)', borderRadius: 12, padding: 20, color: 'var(--dsw-alias-state-error-primary, #e34d59)', background: 'var(--dsw-alias-state-error-bg, rgba(227,77,89,.08))' },
  inlineError: { borderRadius: 8, padding: '9px 12px', color: 'var(--dsw-alias-state-error-primary, #e34d59)', background: 'var(--dsw-alias-state-error-bg, rgba(227,77,89,.08))', fontSize: 13 },
} satisfies Record<string, React.CSSProperties>

const styles = artifactHubWorkspaceStyles

const statusStyles: Record<ShareStatus, React.CSSProperties> = {
  active: { color: 'var(--dsw-alias-state-success-primary, #00a870)', background: 'var(--dsw-alias-state-success-bg, rgba(0,168,112,.10))' },
  expired: { color: 'var(--dsw-alias-label-tertiary, #86909c)', background: 'var(--dsw-alias-bg-module-platform, #f7f8fa)' },
  revoked: { color: 'var(--dsw-alias-state-error-primary, #e34d59)', background: 'var(--dsw-alias-state-error-bg, rgba(227,77,89,.10))' },
}
