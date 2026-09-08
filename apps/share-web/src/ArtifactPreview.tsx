import { useEffect, useState } from 'react'
import { AlertCircle, FileQuestion, LoaderCircle } from 'lucide-react'
import { Highlight, themes } from 'prism-react-renderer'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { codeLanguage, previewKind } from './share'

interface ArtifactPreviewProps {
  readonly name: string
  readonly mimeType: string
  readonly url: string
  readonly canDownload: boolean
}

export function ArtifactPreview({ name, mimeType, url, canDownload }: ArtifactPreviewProps) {
  const kind = previewKind(mimeType, name)

  if (kind === 'image') {
    return <div className="media-preview"><img src={url} alt={name} /></div>
  }
  if (kind === 'pdf') {
    return <iframe className="document-frame" src={url} title={`${name} PDF 预览`} />
  }
  if (kind === 'html') {
    return (
      <iframe
        className="document-frame"
        src={url}
        title={`${name} HTML 预览`}
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
      />
    )
  }
  if (kind === 'unsupported') {
    return (
      <div className="preview-message">
        <FileQuestion aria-hidden="true" />
        <strong>暂不支持在线预览此格式</strong>
        <p>{canDownload ? '你仍然可以下载文件并使用本地应用打开。' : '分享者仅授予了查看权限，暂时无法获取此文件。'}</p>
      </div>
    )
  }
  return (
    <TextPreview
      name={name}
      kind={kind}
      language={kind === 'json' ? 'json' : codeLanguage(mimeType, name)?.grammar ?? 'plain'}
      url={url}
    />
  )
}

interface TextPreviewProps {
  readonly name: string
  readonly kind: 'markdown' | 'json' | 'code'
  readonly language: string
  readonly url: string
}

function TextPreview({ name, kind, language, url }: TextPreviewProps) {
  const [content, setContent] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setContent(null)
    setError(false)
    void fetch(url, { credentials: 'same-origin', signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(`HTTP ${String(response.status)}`)
        return response.text()
      })
      .then(value => { setContent(value) })
      .catch((reason: unknown) => {
        if (!(reason instanceof DOMException && reason.name === 'AbortError')) setError(true)
      })
    return () => { controller.abort() }
  }, [url])

  if (error) {
    return (
      <div className="preview-message">
        <AlertCircle aria-hidden="true" />
        <strong>预览加载失败</strong>
        <p>文件可能已不可用，请刷新页面后重试。</p>
      </div>
    )
  }
  if (content === null) {
    return <div className="preview-loading"><LoaderCircle className="spin" aria-hidden="true" /> 正在载入预览</div>
  }
  if (kind === 'markdown') {
    return (
      <article className="markdown-body">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: props => <a {...props} target="_blank" rel="noreferrer" />,
            img: props => <img {...props} loading="lazy" referrerPolicy="no-referrer" />,
          }}
        >
          {content}
        </ReactMarkdown>
      </article>
    )
  }

  let displayContent = content
  if (kind === 'json') {
    try {
      displayContent = JSON.stringify(JSON.parse(content) as unknown, null, 2)
    } catch {
      // Keep malformed JSON readable instead of turning the entire preview into an error.
    }
  }
  return (
    <Highlight theme={themes.oneDark} code={displayContent} language={language}>
      {({ className, style, tokens, getLineProps, getTokenProps }) => (
        <pre className={`code-preview ${className}`} style={style} aria-label={`${name} 内容`}>
          <code>
            {tokens.map((line, lineIndex) => {
              const lineProps = getLineProps({ line })
              return (
                <span {...lineProps} className={`code-line ${lineProps.className}`} key={lineIndex}>
                  <span className="code-line-number" aria-hidden="true">{lineIndex + 1}</span>
                  <span className="code-line-content">
                    {line.map((token, tokenIndex) => (
                      <span key={tokenIndex} {...getTokenProps({ token })} />
                    ))}
                  </span>
                </span>
              )
            })}
          </code>
        </pre>
      )}
    </Highlight>
  )
}
