import { useEffect, useRef, useState } from 'react'
import type { CreatedSharesRequester, LocalShareRequester } from './api.ts'
import { matchCreatedShare, toDatetimeLocalValue } from './shareLookup.ts'

/** Localized text function injected by the DSH slot renderer. */
export type Translate = (key: string, parameters?: Readonly<Record<string, string>>) => string

/** Props for one file's Local sharing dialog. */
export interface ShareDialogProps {
  readonly sessionId: string
  readonly sourcePath: string
  readonly t: Translate
  readonly requestShare: LocalShareRequester
  readonly requestShares?: CreatedSharesRequester
  readonly onClose: () => void
}

/** Collect Local Share options, publish the snapshot, and show the current URL. */
export function ShareDialog({ sessionId, sourcePath, t, requestShare, requestShares, onClose }: ShareDialogProps) {
  const [expiresAt, setExpiresAt] = useState('')
  const [savedExpiresAt, setSavedExpiresAt] = useState('')
  const [state, setState] = useState<'idle' | 'sharing' | 'success' | 'error'>('idle')
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const [alreadyShared, setAlreadyShared] = useState(false)
  const [existingUrl, setExistingUrl] = useState<string | null>(null)
  const [updated, setUpdated] = useState(false)
  const [copied, setCopied] = useState(false)
  const requestSharesRef = useRef(requestShares)
  requestSharesRef.current = requestShares
  const copiedTimerRef = useRef<number | undefined>(undefined)

  useEffect(() => () => {
    window.clearTimeout(copiedTimerRef.current)
  }, [])

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key === 'Escape' && state !== 'sharing') onClose()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => { document.removeEventListener('keydown', closeOnEscape) }
  }, [onClose, state])

  useEffect(() => {
    const requester = requestSharesRef.current
    if (requester === undefined) return
    const abort = new AbortController()
    requester(abort.signal)
      .then(shares => {
        const existing = matchCreatedShare(shares, sessionId, sourcePath)
        if (existing === null) return
        // Restore the previous options without clobbering fresh user input:
        // a value typed before the fetch lands counts as an intentional edit.
        const restored = toDatetimeLocalValue(existing.expiresAt)
        setExpiresAt(current => current === '' ? restored : current)
        setSavedExpiresAt(restored)
        if (existing.shareUrl !== null) setExistingUrl(existing.shareUrl)
        else setAlreadyShared(true)
      })
      .catch(() => { /* the hint is best-effort and must never block the form */ })
    return () => { abort.abort() }
  }, [sessionId, sourcePath])

  /** Persist the current options through the idempotent share endpoint. */
  const share = async (): Promise<string | null> => {
    const updating = existingUrl !== null
    setState('sharing')
    setError('')
    try {
      const result = await requestShare({
        sessionId,
        sourcePath,
        ...(expiresAt === '' ? {} : { expiresAt: new Date(expiresAt).toISOString() }),
      })
      setUrl(result.url)
      setSavedExpiresAt(expiresAt)
      setUpdated(updating)
      setState('success')
      return result.url
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : String(reason))
      setState('error')
      return null
    }
  }

  const link = url !== '' ? url : existingUrl ?? ''
  const expiryDirty = expiresAt !== savedExpiresAt

  const copy = async (): Promise<void> => {
    if (state === 'sharing') return
    let target = link
    if (expiryDirty) {
      // The edited expiry must reach the Hub before the link leaves the dialog.
      const fresh = await share()
      if (fresh === null) return
      target = fresh
    }
    try {
      await navigator.clipboard.writeText(target)
    } catch {
      return
    }
    window.clearTimeout(copiedTimerRef.current)
    copiedTimerRef.current = window.setTimeout(() => { setCopied(false) }, 2000)
    setCopied(true)
  }

  const open = async (event: React.MouseEvent<HTMLAnchorElement>): Promise<void> => {
    if (state === 'sharing') {
      event.preventDefault()
      return
    }
    if (!expiryDirty) return
    event.preventDefault()
    const fresh = await share()
    if (fresh !== null) window.open(fresh, '_blank', 'noreferrer')
  }

  return (
    <div style={styles.backdrop} role="presentation" onMouseDown={(event) => {
      if (event.currentTarget === event.target && state !== 'sharing') onClose()
    }}>
      <section style={styles.dialog} role="dialog" aria-modal="true" aria-labelledby="artifact-share-title">
        <header style={styles.header}>
          <div>
            <h2 id="artifact-share-title" style={styles.title}>{t('dialog.title')}</h2>
            <div style={styles.path} title={sourcePath}>{sourcePath}</div>
          </div>
          <button type="button" style={styles.iconButton} disabled={state === 'sharing'} aria-label={t('dialog.close')} onClick={onClose}>×</button>
        </header>

        {state === 'success' && existingUrl === null
          ? (
            <div style={styles.body}>
              <p style={styles.success}>{t('dialog.success')}</p>
              <a style={styles.link} href={url} target="_blank" rel="noreferrer">{url}</a>
              <div style={styles.actions}>
                {copied && <span style={styles.copied} role="status">✓ {t('dialog.copied')}</span>}
                <button type="button" style={styles.secondaryButton} onClick={() => { void copy() }}>{t('dialog.copy')}</button>
                <a style={styles.primaryLink} href={url} target="_blank" rel="noreferrer">{t('dialog.open')}</a>
              </div>
            </div>
          )
          : existingUrl !== null
            ? (
              <form style={styles.body} onSubmit={(event) => { event.preventDefault(); void copy() }}>
                <div style={styles.field}>
                  <span style={styles.label}>{t('dialog.visibility')}</span>
                  <div style={styles.fixedValue}>{t('dialog.visibility.link')}</div>
                </div>
                <div style={styles.field}>
                  <span style={styles.label}>{t('dialog.permission')}</span>
                  <div style={styles.fixedValue}>{t('dialog.permission.download')}</div>
                </div>
                <label style={styles.field}>
                  <span style={styles.label}>{t('dialog.expires')}</span>
                  <input
                    style={styles.control}
                    type="datetime-local"
                    value={expiresAt}
                    disabled={state === 'sharing'}
                    onChange={event => { setUpdated(false); setExpiresAt(event.target.value) }}
                  />
                </label>
                {updated && <p style={styles.success}>{t('dialog.updated')}</p>}
                <p style={styles.hint}>{t('dialog.expiresHint')}</p>
                {state === 'error' && <p style={styles.error} role="alert">{error}</p>}
                <div style={styles.actions}>
                  {copied && <span style={styles.copied} role="status">✓ {t('dialog.copied')}</span>}
                  <button type="submit" style={styles.secondaryButton} disabled={state === 'sharing'} onClick={() => { void copy() }}>{t('dialog.copy')}</button>
                  <a
                    style={{ ...styles.primaryLink, ...(state === 'sharing' ? styles.disabled : {}) }}
                    href={link}
                    target="_blank"
                    rel="noreferrer"
                    onClick={event => { void open(event) }}
                  >
                    {t('dialog.open')}
                  </a>
                </div>
              </form>
            )
            : (
              <form style={styles.body} onSubmit={(event) => { event.preventDefault(); void share() }}>
                <div style={styles.field}>
                  <span style={styles.label}>{t('dialog.visibility')}</span>
                  <div style={styles.fixedValue}>{t('dialog.visibility.link')}</div>
                </div>
                <div style={styles.field}>
                  <span style={styles.label}>{t('dialog.permission')}</span>
                  <div style={styles.fixedValue}>{t('dialog.permission.download')}</div>
                </div>
                <label style={styles.field}>
                  <span style={styles.label}>{t('dialog.expires')}</span>
                  <input style={styles.control} type="datetime-local" value={expiresAt} onChange={event => { setExpiresAt(event.target.value) }} />
                </label>
                {alreadyShared && <p style={styles.hint}>{t('dialog.alreadyShared')}</p>}
                {state === 'error' && <p style={styles.error} role="alert">{error}</p>}
                <div style={styles.actions}>
                  <button type="button" style={styles.secondaryButton} disabled={state === 'sharing'} onClick={onClose}>{t('dialog.cancel')}</button>
                  <button type="submit" style={styles.primaryButton} disabled={state === 'sharing'}>{state === 'sharing' ? t('dialog.sharing') : t('dialog.create')}</button>
                </div>
              </form>
            )}
      </section>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  backdrop: { position: 'fixed', inset: 0, zIndex: 1000, display: 'grid', placeItems: 'center', background: 'var(--dsw-alias-bg-mask-1, rgba(0,0,0,.45))', padding: 24 },
  dialog: { width: 'min(480px, 100%)', borderRadius: 16, background: 'var(--dsw-alias-bg-layer-2, #fff)', color: 'var(--dsw-alias-label-primary, #1f2329)', boxShadow: '0 20px 60px rgba(0,0,0,.2)', overflow: 'hidden' },
  header: { display: 'flex', justifyContent: 'space-between', gap: 16, padding: '20px 22px 14px', borderBottom: '1px solid var(--dsw-alias-border-l2, #e5e6eb)' },
  title: { margin: 0, fontSize: 18, fontWeight: 600 },
  path: { marginTop: 6, maxWidth: 390, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--dsw-alias-label-tertiary, #86909c)', fontSize: 13 },
  iconButton: { border: 0, background: 'transparent', color: 'inherit', fontSize: 24, cursor: 'pointer', lineHeight: 1 },
  body: { display: 'grid', gap: 16, padding: 22 },
  field: { display: 'grid', gap: 7 },
  label: { fontSize: 13, fontWeight: 500 },
  control: { width: '100%', boxSizing: 'border-box', minHeight: 38, borderRadius: 8, border: '1px solid var(--dsw-alias-border-l3, #d9dce1)', background: 'var(--dsw-alias-bg-layer-1, #fff)', color: 'inherit', padding: '7px 10px' },
  fixedValue: { color: 'var(--dsw-alias-label-secondary, #4e5969)', fontSize: 14 },
  actions: { display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 4 },
  primaryButton: { border: 0, borderRadius: 8, padding: '8px 15px', background: 'var(--dsw-alias-button-primary-fill, #1f2329)', color: 'var(--dsw-alias-label-primary-foreground, #fff)', cursor: 'pointer' },
  secondaryButton: { border: '1px solid var(--dsw-alias-border-l3, #d9dce1)', borderRadius: 8, padding: '8px 15px', background: 'transparent', color: 'inherit', cursor: 'pointer' },
  primaryLink: { borderRadius: 8, padding: '8px 15px', background: 'var(--dsw-alias-button-primary-fill, #1f2329)', color: 'var(--dsw-alias-label-primary-foreground, #fff)', textDecoration: 'none' },
  success: { margin: 0, color: 'var(--dsw-alias-state-success-primary, #00a870)' },
  link: { overflowWrap: 'anywhere', color: 'var(--dsw-alias-link, #4d6bfe)' },
  error: { margin: 0, color: 'var(--dsw-alias-state-error-primary, #e34d59)', fontSize: 13 },
  hint: { margin: 0, color: 'var(--dsw-alias-label-tertiary, #86909c)', fontSize: 13 },
  disabled: { opacity: 0.5, cursor: 'wait' },
  copied: { alignSelf: 'center', color: 'var(--dsw-alias-state-success-primary, #00a870)', fontSize: 13 },
}
