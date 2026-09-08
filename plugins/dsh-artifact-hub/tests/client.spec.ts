import { describe, expect, it, vi } from 'vitest'
import { requestCreatedShares, requestLocalShare } from '../src/client/api.ts'
import {
  artifactHubWorkspaceStyles,
  filterArtifactGroups,
  groupCreatedShares,
  selectVisibleVersionShares,
} from '../src/client/ArtifactHubWorkspace.tsx'
import type { CreatedShare } from '../src/contracts.ts'
import { artifactFilesStyles, sessionRelativePath } from '../src/client/ArtifactFiles.tsx'
import { matchCreatedShare, toDatetimeLocalValue } from '../src/client/shareLookup.ts'
import { producedFiles } from '../src/client/deliverables.ts'
import { en, zh } from '../src/client/locales.ts'
import { ArtifactHubWorkspaceController } from '../src/client/workspace-controller.ts'

describe('requestLocalShare', () => {
  it('calls the Local share endpoint through DSH Connection RPC', async () => {
    const result = {
      shareId: 'shr_1', artifactId: 'art_1', artifactVersionId: 'av_1', version: 1,
      name: 'report.md', url: 'https://share.example/s/token', expiresAt: null,
    }
    const call = vi.fn(async () => ({ ok: true as const, value: result }))

    await expect(requestLocalShare({
      sessionId: 'sess-1',
      sourcePath: 'report.md',
      expiresAt: '2026-12-31T16:00:00.000Z',
    }, { call })).resolves.toEqual(result)
    expect(call).toHaveBeenCalledWith('/artifact-hub', 'shares', {
      sessionId: 'sess-1',
      sourcePath: 'report.md',
      expiresAt: '2026-12-31T16:00:00.000Z',
    }, undefined)
  })

  it('surfaces the Host error message', async () => {
    await expect(requestLocalShare({
      sessionId: 'sess-1',
      sourcePath: 'missing.md',
    }, { call: async () => ({
      ok: false,
      error: { code: 'internal', message: 'not found', details: {} },
    }) }))
      .rejects.toThrow('not found')
  })
})

describe('requestCreatedShares', () => {
  it('loads the trusted creator list through a payload-free endpoint', async () => {
    const shares = [{
      shareId: 'share-1', artifactId: 'artifact-1', artifactVersionId: 'version-1',
      version: 1, name: 'report.md', sourceSessionId: 'sess-1', sourcePath: 'report.md',
      mimeType: 'text/markdown', size: 42,
      visibility: 'LINK' as const, permission: 'VIEW_DOWNLOAD' as const,
      createdAt: '2026-09-07T10:00:00Z', expiresAt: null, revokedAt: null,
      previewUrl: 'https://share.example/s/preview.ticket',
      shareUrl: 'https://share.example/s/token',
    }]
    const call = vi.fn(async () => ({ ok: true as const, value: shares }))

    await expect(requestCreatedShares({ call })).resolves.toEqual(shares)
    expect(call).toHaveBeenCalledWith('/artifact-hub', 'created-shares', {}, undefined)
  })

  it('rejects unsafe or incomplete share metadata', async () => {
    await expect(requestCreatedShares({ call: async () => ({
      ok: true,
      value: [{ shareId: 'share-1', storageKey: '/private/path' }],
    }) })).rejects.toThrow('invalid created-share list')
  })

  it('rejects a share record without source fields', async () => {
    await expect(requestCreatedShares({ call: async () => ({
      ok: true,
      value: [{
        shareId: 'share-1', artifactId: 'artifact-1', artifactVersionId: 'version-1',
        version: 1, name: 'report.md', mimeType: 'text/markdown', size: 42,
        visibility: 'LINK', permission: 'VIEW_DOWNLOAD',
        createdAt: '2026-09-07T10:00:00Z', expiresAt: null, revokedAt: null,
        previewUrl: null,
      }],
    }) })).rejects.toThrow('invalid created-share list')
  })
})

describe('matchCreatedShare', () => {
  const share = (overrides: Partial<CreatedShare>): CreatedShare => ({
    shareId: 'share-1', artifactId: 'artifact-1', artifactVersionId: 'version-1',
    version: 1, name: 'report.md', sourceSessionId: 'sess-1', sourcePath: 'report.md',
    mimeType: 'text/markdown', size: 42,
    visibility: 'LINK', permission: 'VIEW_DOWNLOAD',
    createdAt: '2026-09-07T10:00:00Z', expiresAt: null, revokedAt: null,
    previewUrl: null,
    shareUrl: null,
    ...overrides,
  })

  it('matches the current session and source path', () => {
    const existing = share({})
    expect(matchCreatedShare([existing], 'sess-1', 'report.md')).toBe(existing)
    expect(matchCreatedShare([existing], 'sess-2', 'report.md')).toBeNull()
    expect(matchCreatedShare([existing], 'sess-1', 'other.md')).toBeNull()
  })

  it('normalizes Windows and POSIX separators on both sides', () => {
    const existing = share({ sourcePath: 'reports\\report.md' })
    expect(matchCreatedShare([existing], 'sess-1', 'reports/report.md')).toBe(existing)
    const posixStored = share({ sourcePath: 'reports/report.md' })
    expect(matchCreatedShare([posixStored], 'sess-1', 'reports\\report.md')).toBe(posixStored)
  })

  it('ignores revoked shares but keeps expired ones', () => {
    const revoked = share({ shareId: 'share-revoked', revokedAt: '2026-09-07T12:00:00Z' })
    expect(matchCreatedShare([revoked], 'sess-1', 'report.md')).toBeNull()
    const expired = share({ shareId: 'share-expired', expiresAt: '2000-01-01T00:00:00Z' })
    expect(matchCreatedShare([expired], 'sess-1', 'report.md')).toBe(expired)
  })

  it('prefers the highest matching version as a defensive tie-break', () => {
    const v1 = share({ shareId: 'share-v1', version: 1 })
    const v2 = share({ shareId: 'share-v2', version: 2 })
    expect(matchCreatedShare([v1, v2], 'sess-1', 'report.md')?.shareId).toBe('share-v2')
  })

  it('returns null when nothing matches', () => {
    expect(matchCreatedShare([], 'sess-1', 'report.md')).toBeNull()
  })
})

describe('toDatetimeLocalValue', () => {
  it('renders an ISO timestamp as a local datetime-local value', () => {
    const date = new Date(2026, 8, 8, 9, 5)
    const expected = '2026-09-08T09:05'
    expect(toDatetimeLocalValue(date.toISOString())).toBe(expected)
  })

  it('returns an empty string for null and invalid input', () => {
    expect(toDatetimeLocalValue(null)).toBe('')
    expect(toDatetimeLocalValue('not-a-timestamp')).toBe('')
  })
})

describe('Share Center grouping and filtering', () => {
  const shares: readonly CreatedShare[] = [
    {
      shareId: 'share-new', artifactId: 'artifact-a', artifactVersionId: 'version-a2',
      version: 2, name: 'report.md', sourceSessionId: 'sess-a', sourcePath: 'report.md',
      mimeType: 'text/markdown', size: 84,
      visibility: 'LINK', permission: 'VIEW_DOWNLOAD', createdAt: '2026-09-07T11:00:00Z',
      expiresAt: '2099-01-01T00:00:00Z', revokedAt: null,
      previewUrl: 'https://share.example/s/preview.new',
      shareUrl: 'https://share.example/s/token.new',
    },
    {
      shareId: 'share-old', artifactId: 'artifact-a', artifactVersionId: 'version-a1',
      version: 1, name: 'report.md', sourceSessionId: 'sess-a', sourcePath: 'report.md',
      mimeType: 'text/markdown', size: 42,
      visibility: 'LINK', permission: 'VIEW_DOWNLOAD', createdAt: '2026-09-07T10:00:00Z',
      expiresAt: '2000-01-01T00:00:00Z', revokedAt: null, previewUrl: null,
      shareUrl: 'https://share.example/s/token.old',
    },
    {
      shareId: 'share-same-name', artifactId: 'artifact-b', artifactVersionId: 'version-b1',
      version: 1, name: 'report.md', sourceSessionId: 'sess-b', sourcePath: 'report.md',
      mimeType: 'text/markdown', size: 21,
      visibility: 'LINK', permission: 'VIEW_DOWNLOAD', createdAt: '2026-09-07T09:00:00Z',
      expiresAt: null, revokedAt: null, previewUrl: 'https://share.example/s/preview.other',
      shareUrl: 'https://share.example/s/token.other',
    },
  ]

  it('groups by stable artifact ID while keeping same-name artifacts separate', () => {
    const groups = groupCreatedShares(shares)
    expect(groups).toHaveLength(2)
    expect(groups[0]?.shares.map(share => share.version)).toEqual([2, 1])
    expect(groups[1]?.artifactId).toBe('artifact-b')
  })

  it('filters records by status and searches versions', () => {
    const groups = groupCreatedShares(shares)
    expect(filterArtifactGroups(groups, '', 'expired')).toMatchObject([
      { artifactId: 'artifact-a', shares: [{ shareId: 'share-old' }] },
    ])
    expect(filterArtifactGroups(groups, 'v2', 'all')).toMatchObject([
      { artifactId: 'artifact-a', shares: [{ shareId: 'share-new' }] },
    ])
  })

  it('shows the newest three versions until the Artifact is expanded', () => {
    const versions = [2, 5, 1, 4, 3].map(version => ({
      ...shares[0]!,
      shareId: `share-${String(version)}`,
      artifactVersionId: `version-${String(version)}`,
      version,
    }))

    expect(
      selectVisibleVersionShares(versions, false).map(share => share.version),
    ).toEqual([5, 4, 3])
    expect(
      selectVisibleVersionShares(versions, true).map(share => share.version),
    ).toEqual([5, 4, 3, 2, 1])
    expect(versions.map(share => share.version)).toEqual([2, 5, 1, 4, 3])
  })
})

describe('producedFiles', () => {
  it('keeps first-seen paths settled no later than the closing response', () => {
    const paths = producedFiles({
      seq: 12,
      turn: { data: { get: () => ({ produced: [
        { seq: 9, path: 'report.md' },
        { seq: 10, path: 'report.md' },
        { seq: 13, path: 'late.md' },
        { seq: 11, path: 'data.csv' },
      ] }) } },
      openFile: vi.fn(),
    })
    expect(paths).toEqual(['report.md', 'data.csv'])
  })

  it('declines when DSH has no valid deliverables data', () => {
    expect(producedFiles({
      seq: 1,
      turn: { data: { get: () => ({ produced: [{ seq: 'bad', path: 'x' }] }) } },
      openFile: vi.fn(),
    })).toBeNull()
  })
})

describe('sessionRelativePath', () => {
  it('keeps safe relative paths and removes dot segments', () => {
    expect(sessionRelativePath('./reports/report.md')).toBe('reports/report.md')
    expect(sessionRelativePath('../outside.md')).toBeNull()
  })

  it('relativizes POSIX and Windows files inside the Session cwd', () => {
    expect(sessionRelativePath('/data/sessions/sess-1/report.md', '/data/sessions/sess-1'))
      .toBe('report.md')
    expect(sessionRelativePath('C:\\Sessions\\One\\report.md', 'c:\\sessions\\one'))
      .toBe('report.md')
  })

  it('rejects absolute files outside the Session cwd', () => {
    expect(sessionRelativePath('/data/other/report.md', '/data/sessions/sess-1')).toBeNull()
    expect(sessionRelativePath('/data/sessions/sess-1/report.md')).toBeNull()
  })
})

describe('ArtifactFiles theme', () => {
  it('uses the host theme tokens for a readable file chip in either color scheme', () => {
    expect(artifactFilesStyles.file).toMatchObject({
      background: 'var(--dsw-alias-bg-module-platform, #f7f8fa)',
      border: '1px solid var(--dsw-alias-border-l2, #e5e6eb)',
    })
    expect(artifactFilesStyles.openButton).toMatchObject({
      color: 'var(--dsw-alias-label-primary, #1f2329)',
    })
  })

  it('uses host theme tokens for the Share Center surface', () => {
    expect(artifactHubWorkspaceStyles.panel).toMatchObject({
      background: 'var(--dsw-alias-bg-base, #fff)',
      color: 'var(--dsw-alias-label-primary, #1f2329)',
    })
    expect(artifactHubWorkspaceStyles.card).toMatchObject({
      border: '1px solid var(--dsw-alias-border-l2, #e5e6eb)',
      background: 'var(--dsw-alias-bg-layer-1, #fff)',
    })
  })

  it('uses the version group as the only horizontal row separator', () => {
    expect(artifactHubWorkspaceStyles.versionGroup).toHaveProperty(
      'borderBottom',
      '1px solid var(--dsw-alias-border-l3, #f0f1f2)',
    )
    expect(artifactHubWorkspaceStyles.shareRow).not.toHaveProperty('borderBottom')
  })
})

describe('Share Center product copy', () => {
  it('uses file terminology instead of exposing Artifact terminology', () => {
    expect(zh['center.subtitle']).toBe('按文件汇总各版本当前的分享')
    expect(zh['center.results']).toBe('{files} 个文件 · {shares} 条分享')
    expect(en['center.subtitle']).toBe('Files are grouped with each version’s current share.')
    expect(en['center.results']).toBe('{files} files · {shares} shares')
    expect(zh).not.toHaveProperty('center.activeCount')
    expect(en).not.toHaveProperty('center.activeCount')
  })
})

describe('ArtifactHubWorkspaceController', () => {
  it('shares open state between the sidebar launcher and workspace', () => {
    const controller = new ArtifactHubWorkspaceController()
    const listener = vi.fn()
    const unsubscribe = controller.subscribe(listener)

    controller.open()
    expect(controller.getSnapshot()).toEqual({ open: true })
    controller.close()
    expect(controller.getSnapshot()).toEqual({ open: false })
    expect(listener).toHaveBeenCalledTimes(2)
    unsubscribe()
  })
})
