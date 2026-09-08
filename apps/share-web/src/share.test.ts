import { describe, expect, it } from 'vitest'
import { codeLanguage, displayMimeType, formatFileSize, previewKind, shareTokenFromPath } from './share'

describe('shareTokenFromPath', () => {
  it('extracts one URL-safe token from the public share route', () => {
    expect(shareTokenFromPath('/s/abc_123-xyz')).toBe('abc_123-xyz')
    expect(shareTokenFromPath('/s/abc_123-xyz/')).toBe('abc_123-xyz')
    expect(shareTokenFromPath('/s/preview.share-id.123.signature')).toBe('preview.share-id.123.signature')
  })

  it('rejects unrelated or nested routes', () => {
    expect(shareTokenFromPath('/')).toBeNull()
    expect(shareTokenFromPath('/s/token/content')).toBeNull()
  })
})

describe('previewKind', () => {
  it('selects safe viewers from MIME type and extension', () => {
    expect(previewKind('text/markdown', 'report.md')).toBe('markdown')
    expect(previewKind('application/octet-stream', 'report.json')).toBe('json')
    expect(previewKind('text/html; charset=utf-8', 'report.html')).toBe('html')
    expect(previewKind('application/pdf', 'report.pdf')).toBe('pdf')
    expect(previewKind('image/png', 'chart.png')).toBe('image')
    expect(previewKind('application/zip', 'bundle.zip')).toBe('unsupported')
  })

  it.each([
    ['main.py', 'python', 'Python'],
    ['query.sql', 'sql', 'SQL'],
    ['server.ts', 'typescript', 'TypeScript'],
    ['App.tsx', 'tsx', 'TSX'],
    ['main.go', 'go', 'Go'],
    ['lib.rs', 'rust', 'Rust'],
    ['service.java', 'clike', 'Java'],
    ['Dockerfile', 'plain', 'Dockerfile'],
  ])('previews octet-stream source %s with the %s grammar', (name, grammar, label) => {
    expect(previewKind('application/octet-stream', name)).toBe('code')
    expect(codeLanguage('application/octet-stream', name)).toEqual({ grammar, label })
    expect(displayMimeType('application/octet-stream', name)).toBe(label)
  })

  it('prefers a source extension when a server reports a generic HTML MIME type', () => {
    expect(previewKind('text/html', 'legacy.php')).toBe('code')
    expect(previewKind('text/html', 'component.vue')).toBe('code')
    expect(previewKind('text/html', 'index.html')).toBe('html')
  })
})

describe('formatFileSize', () => {
  it('formats bytes into a compact human-readable value', () => {
    expect(formatFileSize(800)).toBe('800 B')
    expect(formatFileSize(2048)).toBe('2.00 KB')
    expect(formatFileSize(5 * 1024 * 1024)).toBe('5.00 MB')
  })
})
