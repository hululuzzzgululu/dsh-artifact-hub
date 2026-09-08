import { describe, expect, it, vi } from 'vitest'
import { ArtifactHubClient, type Fetch, inferArtifactType } from '../src/host/client.ts'
import {
  handleCreatedSharesRequest,
  handleLocalShareRequest,
  registerLocalShareRoute,
} from '../src/host/route.ts'

const HUB_RESULT = {
  share_id: 'shr_1',
  artifact_id: 'art_1',
  artifact_version_id: 'av_1',
  version: 1,
  name: 'report.md',
  url: 'https://share.example/s/token',
  expires_at: null,
  token: 'must-not-reach-browser',
}

const HOST_SESSIONS = {
  get: (sessionId: string) => sessionId === 'sess-1'
    ? { header: { cwd: '/workspaces/project-one' } }
    : undefined,
}

const HOST_WORKSPACES = {
  list: () => [{
    id: 'workspace-1',
    path: '/workspaces/project-one',
    title: 'Project One',
    sessionIds: ['sess-1'],
  }],
}

const HUB_IDENTITY = { createdById: 'user-1', createdByName: 'User One' }

const HUB_LIST_ITEM = {
  ...HUB_RESULT,
  mime_type: 'text/markdown',
  storage_mode: 'LOCAL',
  storage_key: '/private/snapshot/path',
  size: 42,
  checksum: 'must-not-reach-browser',
  visibility: 'LINK',
  permission: 'VIEW_DOWNLOAD',
  created_by_id: 'user-1',
  created_by_name: 'User One',
  created_at: '2026-09-07T10:00:00Z',
  revoked_at: null,
  url: 'https://share.example/s/preview.ticket',
}

describe('registerLocalShareRoute', () => {
  it('registers through connection.rpc as exposed by DSH 0.1.1', () => {
    const dispose = vi.fn(async () => {})
    const handle = vi.fn(() => dispose)
    const client = new ArtifactHubClient('http://hub.internal', HUB_IDENTITY)

    expect(() => registerLocalShareRoute(
      { handle } as never,
      client,
      HOST_SESSIONS,
      HOST_WORKSPACES,
    )).not.toThrow()
    expect(handle).toHaveBeenCalledWith(
      '/artifact-hub',
      expect.any(Function),
      { authority: 'loopback' },
    )
  })

  it('dispatches the Share Center list endpoint', async () => {
    let handler: ((endpoint: string, payload: unknown, signal: AbortSignal) => Promise<unknown>) | undefined
    const handle = vi.fn((_channel, value) => {
      handler = value
      return async () => {}
    })
    const client = new ArtifactHubClient('http://hub.internal', HUB_IDENTITY, async () =>
      Response.json({ resultCode: '0', resultMsg: 'success', resultObj: { items: [HUB_LIST_ITEM] } }))
    registerLocalShareRoute({ handle } as never, client, HOST_SESSIONS, HOST_WORKSPACES)

    await expect(handler?.('created-shares', {}, new AbortController().signal)).resolves.toMatchObject({
      ok: true,
      value: [{ shareId: 'shr_1', name: 'report.md' }],
    })
  })
})

describe('ArtifactHubClient', () => {
  it('maps a Local request, adds trusted identity, and removes the raw token', async () => {
    const fetcher = vi.fn<Fetch>(async () => Response.json({
      resultCode: '0',
      resultMsg: 'success',
      resultObj: HUB_RESULT,
    }, { status: 201 }))
    const client = new ArtifactHubClient(
      'http://hub.internal:8000/base',
      HUB_IDENTITY,
      fetcher,
    )

    const result = await client.createLocalShare({
      sessionId: 'sess-1',
      workspaceRoot: '/workspaces/project-one',
      dshWorkspaceId: 'workspace-1',
      dshWorkspacePath: '/workspaces/project-one',
      dshWorkspaceTitle: 'Project One',
      sourcePath: 'reports/report.md',
      expiresAt: '2026-12-31T16:00:00.000Z',
    })

    expect(fetcher).toHaveBeenCalledOnce()
    const [url, init] = fetcher.mock.calls[0]!
    expect(String(url)).toBe('http://hub.internal:8000/api/shares')
    expect(JSON.parse(String(init?.body))).toEqual({
      session_id: 'sess-1',
      workspace_root: '/workspaces/project-one',
      source_path: 'reports/report.md',
      artifact_type: 'markdown',
      created_by_id: 'user-1',
      created_by_name: 'User One',
      dsh_workspace_id: 'workspace-1',
      dsh_workspace_path: '/workspaces/project-one',
      dsh_workspace_title: 'Project One',
      expires_at: '2026-12-31T16:00:00.000Z',
    })
    expect(result).toEqual({
      shareId: 'shr_1',
      artifactId: 'art_1',
      artifactVersionId: 'av_1',
      version: 1,
      name: 'report.md',
      url: 'https://share.example/s/token',
      expiresAt: null,
    })
    expect(result).not.toHaveProperty('token')
  })

  it('lists the trusted creator shares and strips storage metadata', async () => {
    const fetcher = vi.fn<Fetch>(async () => Response.json({
      resultCode: '0', resultMsg: 'success', resultObj: { items: [HUB_LIST_ITEM] },
    }))
    const client = new ArtifactHubClient('http://hub.internal', HUB_IDENTITY, fetcher)

    const shares = await client.listCreatedShares()

    const [url, init] = fetcher.mock.calls[0]!
    expect(String(url)).toBe('http://hub.internal/api/shares?created_by_id=user-1')
    expect(init).toMatchObject({ method: 'GET' })
    expect(shares).toEqual([{
      shareId: 'shr_1', artifactId: 'art_1', artifactVersionId: 'av_1', version: 1,
      name: 'report.md', mimeType: 'text/markdown', size: 42,
      visibility: 'LINK', permission: 'VIEW_DOWNLOAD',
      createdAt: '2026-09-07T10:00:00Z', expiresAt: null, revokedAt: null,
      previewUrl: 'https://share.example/s/preview.ticket',
    }])
    expect(shares[0]).not.toHaveProperty('storageKey')
    expect(shares[0]).not.toHaveProperty('checksum')
  })
})

describe('inferArtifactType', () => {
  it('classifies common Session file outputs by extension', () => {
    expect(inferArtifactType('reports/report.md')).toBe('markdown')
    expect(inferArtifactType('preview.HTML')).toBe('html')
    expect(inferArtifactType('charts\\figure.png')).toBe('image')
    expect(inferArtifactType('data.csv')).toBe('data')
    expect(inferArtifactType('script.py')).toBe('code')
    expect(inferArtifactType('bundle.zip')).toBe('archive')
  })

  it('falls back to other for unknown, missing, or dotfile extensions', () => {
    expect(inferArtifactType('binary')).toBe('other')
    expect(inferArtifactType('.gitignore')).toBe('other')
    expect(inferArtifactType('weird.')).toBe('other')
    expect(inferArtifactType('file.xyz')).toBe('other')
  })
})

describe('handleCreatedSharesRequest', () => {
  it('returns the browser-safe trusted creator list', async () => {
    const client = new ArtifactHubClient('http://hub.internal', HUB_IDENTITY, async () =>
      Response.json({ resultCode: '0', resultMsg: 'success', resultObj: { items: [HUB_LIST_ITEM] } }))

    await expect(handleCreatedSharesRequest(client)).resolves.toMatchObject({
      ok: true,
      value: [{ shareId: 'shr_1', artifactId: 'art_1' }],
    })
  })
})

describe('handleLocalShareRequest', () => {
  it('resolves the authoritative workspace from the Host session store', async () => {
    const fetcher = vi.fn<Fetch>(async () => Response.json({
      resultCode: '0', resultMsg: 'success', resultObj: HUB_RESULT,
    }, { status: 201 }))
    const client = new ArtifactHubClient('http://hub.internal', HUB_IDENTITY, fetcher)
    const response = await handleLocalShareRequest({
      sessionId: 'sess-1',
      sourcePath: 'report.md',
      workspaceRoot: '/browser-must-not-control-this',
    }, client, HOST_SESSIONS, HOST_WORKSPACES)

    expect(response).toMatchObject({ ok: true })
    const [, init] = fetcher.mock.calls[0]!
    expect(JSON.parse(String(init?.body))).toMatchObject({
      session_id: 'sess-1',
      workspace_root: '/workspaces/project-one',
      source_path: 'report.md',
      dsh_workspace_id: 'workspace-1',
      dsh_workspace_path: '/workspaces/project-one',
      dsh_workspace_title: 'Project One',
    })
  })

  it('returns a browser-safe success result', async () => {
    const client = new ArtifactHubClient('http://hub.internal', HUB_IDENTITY, async () =>
      Response.json({ resultCode: '0', resultMsg: 'success', resultObj: HUB_RESULT }, { status: 201 }))
    const response = await handleLocalShareRequest({
      sessionId: 'sess-1',
      sourcePath: 'report.md',
    }, client, HOST_SESSIONS, HOST_WORKSPACES)

    expect(response).toEqual({
      ok: true,
      value: expect.objectContaining({ shareId: 'shr_1', version: 1 }),
    })
  })

  it('falls back to the trusted session path for an unregistered legacy Session', async () => {
    const fetcher = vi.fn<Fetch>(async () => Response.json({
      resultCode: '0', resultMsg: 'success', resultObj: HUB_RESULT,
    }, { status: 201 }))
    const client = new ArtifactHubClient('http://hub.internal', HUB_IDENTITY, fetcher)

    await handleLocalShareRequest(
      { sessionId: 'sess-1', sourcePath: 'report.md' },
      client,
      HOST_SESSIONS,
      { list: () => [{ ...HOST_WORKSPACES.list()[0]!, sessionIds: ['another-session'] }] },
    )

    const [, init] = fetcher.mock.calls[0]!
    const body = JSON.parse(String(init?.body)) as Readonly<Record<string, unknown>>
    expect(body.dsh_workspace_path).toBe('/workspaces/project-one')
    expect(body).not.toHaveProperty('dsh_workspace_id')
    expect(body).not.toHaveProperty('dsh_workspace_title')
  })

  it.each(['/absolute.md', '../outside.md', 'nested/../../outside.md', 'C:\\outside.md'])('rejects unsafe source path %s', async (sourcePath) => {
    const fetcher = vi.fn<Fetch>()
    const client = new ArtifactHubClient('http://hub.internal', HUB_IDENTITY, fetcher)
    const response = await handleLocalShareRequest({
      sessionId: 'sess-1', sourcePath,
    }, client, HOST_SESSIONS, HOST_WORKSPACES)

    expect(response).toMatchObject({ ok: false, error: { code: 'bad-request' } })
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('preserves a Hub validation message', async () => {
    const client = new ArtifactHubClient('http://hub.internal', HUB_IDENTITY, async () =>
      Response.json({ resultCode: '404', resultMsg: 'source Session File does not exist', resultObj: null }, { status: 404 }))
    const response = await handleLocalShareRequest({
      sessionId: 'sess-1', sourcePath: 'missing.md',
    }, client, HOST_SESSIONS, HOST_WORKSPACES)

    expect(response).toMatchObject({
      ok: false,
      error: { message: 'source Session File does not exist' },
    })
  })

  it('rejects a browser request for a session without a live Host workspace', async () => {
    const fetcher = vi.fn<Fetch>()
    const client = new ArtifactHubClient('http://hub.internal', HUB_IDENTITY, fetcher)
    const response = await handleLocalShareRequest({
      sessionId: 'unknown-session',
      sourcePath: 'report.md',
    }, client, HOST_SESSIONS, HOST_WORKSPACES)

    expect(response).toEqual({
      ok: false,
      error: {
        code: 'session-not-found',
        message: 'Session workspace is unavailable',
        details: { sessionId: 'unknown-session' },
      },
    })
    expect(fetcher).not.toHaveBeenCalled()
  })
})
