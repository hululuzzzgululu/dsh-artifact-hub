export type PreviewKind = 'markdown' | 'json' | 'code' | 'image' | 'pdf' | 'html' | 'unsupported'

export interface CodeLanguage {
  /** Prism grammar name. Unsupported grammars intentionally fall back to plain text. */
  readonly grammar: string
  readonly label: string
}

const PLAIN_TEXT: CodeLanguage = { grammar: 'plain', label: '文本' }

const CODE_EXTENSIONS: Readonly<Record<string, CodeLanguage>> = {
  py: { grammar: 'python', label: 'Python' },
  pyw: { grammar: 'python', label: 'Python' },
  sql: { grammar: 'sql', label: 'SQL' },
  ddl: { grammar: 'sql', label: 'SQL' },
  dml: { grammar: 'sql', label: 'SQL' },
  js: { grammar: 'javascript', label: 'JavaScript' },
  mjs: { grammar: 'javascript', label: 'JavaScript' },
  cjs: { grammar: 'javascript', label: 'JavaScript' },
  jsx: { grammar: 'jsx', label: 'JSX' },
  ts: { grammar: 'typescript', label: 'TypeScript' },
  mts: { grammar: 'typescript', label: 'TypeScript' },
  cts: { grammar: 'typescript', label: 'TypeScript' },
  tsx: { grammar: 'tsx', label: 'TSX' },
  java: { grammar: 'clike', label: 'Java' },
  go: { grammar: 'go', label: 'Go' },
  rs: { grammar: 'rust', label: 'Rust' },
  c: { grammar: 'c', label: 'C' },
  h: { grammar: 'c', label: 'C/C++ Header' },
  cc: { grammar: 'cpp', label: 'C++' },
  cpp: { grammar: 'cpp', label: 'C++' },
  cxx: { grammar: 'cpp', label: 'C++' },
  hpp: { grammar: 'cpp', label: 'C++ Header' },
  hxx: { grammar: 'cpp', label: 'C++ Header' },
  cs: { grammar: 'clike', label: 'C#' },
  kt: { grammar: 'kotlin', label: 'Kotlin' },
  kts: { grammar: 'kotlin', label: 'Kotlin' },
  swift: { grammar: 'swift', label: 'Swift' },
  rb: { grammar: 'plain', label: 'Ruby' },
  php: { grammar: 'markup', label: 'PHP' },
  sh: { grammar: 'plain', label: 'Shell' },
  bash: { grammar: 'plain', label: 'Bash' },
  zsh: { grammar: 'plain', label: 'Zsh' },
  fish: { grammar: 'plain', label: 'Fish' },
  css: { grammar: 'css', label: 'CSS' },
  scss: { grammar: 'css', label: 'SCSS' },
  sass: { grammar: 'css', label: 'Sass' },
  less: { grammar: 'css', label: 'Less' },
  xml: { grammar: 'markup', label: 'XML' },
  svg: { grammar: 'markup', label: 'SVG' },
  yaml: { grammar: 'yaml', label: 'YAML' },
  yml: { grammar: 'yaml', label: 'YAML' },
  graphql: { grammar: 'graphql', label: 'GraphQL' },
  gql: { grammar: 'graphql', label: 'GraphQL' },
  vue: { grammar: 'markup', label: 'Vue' },
  svelte: { grammar: 'markup', label: 'Svelte' },
  lua: { grammar: 'plain', label: 'Lua' },
  r: { grammar: 'plain', label: 'R' },
  scala: { grammar: 'clike', label: 'Scala' },
  dart: { grammar: 'clike', label: 'Dart' },
  proto: { grammar: 'clike', label: 'Protocol Buffers' },
  toml: { grammar: 'plain', label: 'TOML' },
  ini: PLAIN_TEXT,
  cfg: PLAIN_TEXT,
  conf: PLAIN_TEXT,
  env: PLAIN_TEXT,
  properties: PLAIN_TEXT,
  csv: PLAIN_TEXT,
  log: PLAIN_TEXT,
  txt: PLAIN_TEXT,
}

const CODE_MIME_TYPES: Readonly<Record<string, CodeLanguage>> = {
  'application/sql': { grammar: 'sql', label: 'SQL' },
  'application/xml': { grammar: 'markup', label: 'XML' },
  'application/yaml': { grammar: 'yaml', label: 'YAML' },
  'text/css': { grammar: 'css', label: 'CSS' },
  'text/csv': PLAIN_TEXT,
  'text/javascript': { grammar: 'javascript', label: 'JavaScript' },
  'text/plain': PLAIN_TEXT,
  'text/typescript': { grammar: 'typescript', label: 'TypeScript' },
  'text/xml': { grammar: 'markup', label: 'XML' },
  'text/yaml': { grammar: 'yaml', label: 'YAML' },
  'text/x-python': { grammar: 'python', label: 'Python' },
}

const CODE_FILENAMES: Readonly<Record<string, CodeLanguage>> = {
  dockerfile: { grammar: 'plain', label: 'Dockerfile' },
  makefile: { grammar: 'plain', label: 'Makefile' },
}

export function shareTokenFromPath(pathname: string): string | null {
  const match = /^\/s\/([^/]+)\/?$/.exec(pathname)
  if (match === null) return null
  try {
    const token = decodeURIComponent(match[1])
    return token.length > 0 ? token : null
  } catch {
    return null
  }
}

export function previewKind(mimeType: string, name: string): PreviewKind {
  const normalized = mimeType.split(';', 1)[0].trim().toLowerCase()
  const extension = fileExtension(name)
  if (normalized === 'text/markdown' || extension === 'md' || extension === 'markdown') return 'markdown'
  if (normalized === 'application/json' || normalized.endsWith('+json') || extension === 'json' || extension === 'ipynb') return 'json'
  if (knownCodeLanguage(mimeType, name) !== null) return 'code'
  if (normalized.startsWith('image/')) return 'image'
  if (normalized === 'application/pdf' || extension === 'pdf') return 'pdf'
  if (normalized === 'text/html' || extension === 'html' || extension === 'htm') return 'html'
  if (normalized.startsWith('text/')) return 'code'
  return 'unsupported'
}

/** Resolve a display label and a bundled Prism grammar for source/config files. */
export function codeLanguage(mimeType: string, name: string): CodeLanguage | null {
  const known = knownCodeLanguage(mimeType, name)
  if (known !== null) return known
  const normalized = mimeType.split(';', 1)[0].trim().toLowerCase()
  return normalized.startsWith('text/') ? PLAIN_TEXT : null
}

function knownCodeLanguage(mimeType: string, name: string): CodeLanguage | null {
  const filename = name.replace(/\\/gu, '/').split('/').pop()?.toLowerCase() ?? ''
  const byFilename = CODE_FILENAMES[filename]
  if (byFilename !== undefined) return byFilename
  const byExtension = CODE_EXTENSIONS[fileExtension(filename)]
  if (byExtension !== undefined) return byExtension
  const normalized = mimeType.split(';', 1)[0].trim().toLowerCase()
  const byMime = CODE_MIME_TYPES[normalized]
  if (byMime !== undefined) return byMime
  return null
}

export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '—'
  if (bytes < 1024) return `${String(bytes)} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  const digits = value >= 100 ? 0 : value >= 10 ? 1 : 2
  return `${value.toFixed(digits)} ${units[unitIndex]}`
}

export function displayMimeType(mimeType: string, name: string): string {
  const kind = previewKind(mimeType, name)
  if (kind === 'code') return codeLanguage(mimeType, name)?.label ?? '文本'
  const labels: Record<PreviewKind, string> = {
    markdown: 'Markdown',
    json: 'JSON',
    code: '文本',
    image: '图片',
    pdf: 'PDF',
    html: 'HTML',
    unsupported: name.includes('.') ? name.split('.').pop()?.toUpperCase() ?? '文件' : '文件',
  }
  return labels[kind]
}

function fileExtension(name: string): string {
  const filename = name.replace(/\\/gu, '/').split('/').pop() ?? ''
  return filename.includes('.') ? filename.split('.').pop()?.toLowerCase() ?? '' : ''
}

export function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}
