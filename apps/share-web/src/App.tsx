import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  CalendarClock,
  Download,
  FileText,
  Link2,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  UserRound,
} from 'lucide-react'
import { ArtifactPreview } from './ArtifactPreview'
import { contentUrl, downloadUrl, fetchPublicShare } from './api'
import { displayMimeType, formatDate, formatFileSize, shareTokenFromPath } from './share'
import { ShareApiError, type PublicShare, type ShareErrorCode } from './types'

type PageState =
  | { readonly kind: 'loading' }
  | { readonly kind: 'ready'; readonly share: PublicShare }
  | { readonly kind: 'error'; readonly code: ShareErrorCode }

const token = shareTokenFromPath(window.location.pathname)

export default function App() {
  const [state, setState] = useState<PageState>(
    token === null ? { kind: 'error', code: 'not_found' } : { kind: 'loading' },
  )

  const loadShare = useCallback(async (signal?: AbortSignal) => {
    if (token === null) return
    setState({ kind: 'loading' })
    try {
      const share = await fetchPublicShare(token, signal)
      setState({ kind: 'ready', share })
      document.title = `${share.name} · DSH 文件分享`
    } catch (reason: unknown) {
      if (reason instanceof DOMException && reason.name === 'AbortError') return
      setState({
        kind: 'error',
        code: reason instanceof ShareApiError ? reason.code : 'unknown',
      })
    }
  }, [])

  useEffect(() => {
    if (token === null) return
    const controller = new AbortController()
    void loadShare(controller.signal)
    return () => { controller.abort() }
  }, [loadShare])

  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="brand" aria-label="DSH 文件分享">
          <span className="brand-mark"><span /></span>
          <span>DSH 文件分享</span>
        </div>
        <span className="security-label"><Link2 aria-hidden="true" /> 链接分享</span>
      </header>

      <main>
        {state.kind === 'loading' && <LoadingPage />}
        {state.kind === 'error' && <ErrorPage code={state.code} onRetry={() => { void loadShare() }} />}
        {state.kind === 'ready' && token !== null && <SharePage share={state.share} token={token} />}
      </main>

      <footer>
        <LockKeyhole aria-hidden="true" />
        由 DSH 安全托管 · 原始内容的后续修改不会影响此文件。
      </footer>
    </div>
  )
}

function SharePage({ share, token }: { readonly share: PublicShare; readonly token: string }) {
  return (
    <section className="share-page" aria-labelledby="artifact-title">
      <div className="artifact-heading">
        <div className="file-symbol"><FileText aria-hidden="true" /></div>
        <div className="title-block">
          <h1 id="artifact-title" title={share.name}>{share.name}</h1>
          <div className="file-facts" aria-label="文件信息">
            <span className="file-type">{displayMimeType(share.mimeType, share.name)}</span>
            <i aria-hidden="true" />
            <span>版本 {share.version}</span>
            <i aria-hidden="true" />
            <span>{formatFileSize(share.size)}</span>
          </div>
          <div className="meta-row">
            <span><UserRound aria-hidden="true" /> 分享者 <strong>{share.createdByName}</strong></span>
            <span><CalendarClock aria-hidden="true" /> 分享于 <time dateTime={share.createdAt}>{formatDate(share.createdAt)}</time></span>
          </div>
        </div>
        <div className="heading-actions">
          <a className="download-button" href={downloadUrl(token)}>
            <Download aria-hidden="true" />
            下载文件
          </a>
          <div className="access-summary" aria-label="分享权限">
            <span className="access-permission"><ShieldCheck aria-hidden="true" /> 可查看和下载</span>
            {share.expiresAt !== null && (
              <span className="access-expiry">有效期至 <time dateTime={share.expiresAt}>{formatDate(share.expiresAt)}</time></span>
            )}
          </div>
        </div>
      </div>

      <div className="preview-card">
        <div className="preview-toolbar">
          <span className="preview-title">文件预览</span>
        </div>
        <div className="preview-surface">
          <ArtifactPreview
            name={share.name}
            mimeType={share.mimeType}
            url={contentUrl(token)}
            canDownload
          />
        </div>
      </div>

    </section>
  )
}

function LoadingPage() {
  return (
    <section className="share-page" aria-label="正在加载分享">
      <div className="artifact-heading loading-heading">
        <div className="skeleton skeleton-square" />
        <div className="title-block">
          <div className="skeleton skeleton-title" />
          <div className="skeleton skeleton-short" />
          <div className="skeleton skeleton-meta" />
        </div>
        <div className="skeleton skeleton-action" />
      </div>
      <div className="preview-card loading-preview">
        <div className="preview-toolbar"><span className="preview-title">文件预览</span></div>
        <div className="preview-surface"><div className="preview-loading">正在安全载入分享内容…</div></div>
      </div>
    </section>
  )
}

const errorContent: Record<ShareErrorCode, { readonly title: string; readonly description: string; readonly retry: boolean }> = {
  share_expired: { title: '分享已过期', description: '这个分享已超过有效期，请联系分享者创建新的链接。', retry: false },
  share_revoked: { title: '分享已被撤销', description: '分享者已停止此链接的访问权限。', retry: false },
  access_restricted: { title: '暂无访问权限', description: '此分享仅对指定企业成员开放，请登录正确的账号后再试。', retry: true },
  not_found: { title: '没有找到这个分享', description: '链接可能不完整，或分享记录已不存在。', retry: false },
  network_error: { title: '连接暂时中断', description: '无法连接到文件分享服务，请检查网络后重试。', retry: true },
  invalid_response: { title: '分享暂时无法打开', description: '服务返回了无法识别的数据，请稍后重试。', retry: true },
  unknown: { title: '分享暂时无法打开', description: '发生了意外错误，请稍后重试。', retry: true },
}

function ErrorPage({ code, onRetry }: { readonly code: ShareErrorCode; readonly onRetry: () => void }) {
  const content = errorContent[code]
  return (
    <section className="error-page" aria-labelledby="error-title">
      <div className="error-icon"><AlertTriangle aria-hidden="true" /></div>
      <span className="error-kicker">DSH 文件分享</span>
      <h1 id="error-title">{content.title}</h1>
      <p>{content.description}</p>
      {content.retry && (
        <button type="button" onClick={onRetry}><RefreshCw aria-hidden="true" /> 重新尝试</button>
      )}
    </section>
  )
}
