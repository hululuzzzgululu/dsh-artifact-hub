import { createHash } from 'node:crypto'
import { access, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import { ArtifactHubClient, type Fetch } from '../src/host/client.ts'
import { resolveShareStorage } from '../src/host/index.ts'
import { handleShareRequest } from '../src/host/route.ts'

const HUB_IDENTITY = { createdById: 'user-1', createdByName: 'User One' }
const HUB_RESULT = {
  share_id: 'shr_1',
  artifact_id: 'art_1',
  artifact_version_id: 'av_1',
  version: 1,
  name: 'report.md',
  url: 'https://share.example/s/token',
  expires_at: null,
}

describe('NAS share flow', () => {
  it('prepares, copies through the DSH mount, and commits the checksum', async () => {
    const fixture = await createFixture()
    try {
      const source = '# generated on the DSH host\n'
      await writeFile(join(fixture.workspace, 'reports', 'report.md'), source)
      const storageKey = 'user-1/artifacts/art_1/v1/report.md'
      const fetcher = vi.fn<Fetch>(async (input, init) => {
        const url = String(input)
        if (url.endsWith('/api/shares/prepare')) {
          return Response.json({
            resultCode: '0',
            resultMsg: 'success',
            resultObj: {
              upload_id: 'upl_1',
              artifact_id: 'art_1',
              version: 1,
              storage_mode: 'NAS',
              storage_key: storageKey,
              target_path: '/different/hub/mount/user-1/artifacts/art_1/v1/report.md',
              name: 'report.md',
            },
          }, { status: 201 })
        }
        expect(url).toMatch(/\/api\/shares\/commit$/u)
        expect(JSON.parse(String(init?.body))).toMatchObject({
          upload_id: 'upl_1',
          created_by_id: 'user-1',
          checksum: createHash('sha256').update(source).digest('hex'),
          expires_at: '2026-12-31T16:00:00.000Z',
        })
        return Response.json({ resultCode: '0', resultMsg: 'success', resultObj: HUB_RESULT }, { status: 201 })
      })
      const client = new ArtifactHubClient('http://hub.internal', HUB_IDENTITY, fetcher)

      const response = await handleShareRequest({
        sessionId: 'sess-1',
        sourcePath: 'reports/report.md',
        expiresAt: '2026-12-31T16:00:00.000Z',
      }, client, fixture.sessions, fixture.workspaces, {
        mode: 'nas',
        artifactRoot: fixture.artifactRoot,
      })

      expect(response).toMatchObject({ ok: true, value: { shareId: 'shr_1' } })
      expect(fetcher).toHaveBeenCalledTimes(2)
      expect(await readFile(join(fixture.artifactRoot, storageKey), 'utf8')).toBe(source)
      expect(await readdir(join(fixture.artifactRoot, 'user-1/artifacts/art_1/v1'))).toEqual(['report.md'])
      const prepareBody = JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body)) as Readonly<Record<string, unknown>>
      expect(prepareBody).not.toHaveProperty('workspace_root')
      expect(prepareBody).toMatchObject({
        session_id: 'sess-1',
        source_path: 'reports/report.md',
        dsh_workspace_id: 'workspace-1',
      })
    } finally {
      await fixture.cleanup()
    }
  })

  it('rejects a storage key that escapes the configured NAS root', async () => {
    const fixture = await createFixture()
    try {
      await writeFile(join(fixture.workspace, 'reports', 'report.md'), 'safe source')
      const fetcher = vi.fn<Fetch>(async () => Response.json({
        resultCode: '0',
        resultMsg: 'success',
        resultObj: {
          upload_id: 'upl_1',
          artifact_id: 'art_1',
          version: 1,
          storage_mode: 'NAS',
          storage_key: '../escaped.md',
          target_path: '/ignored',
          name: 'report.md',
        },
      }, { status: 201 }))
      const client = new ArtifactHubClient('http://hub.internal', HUB_IDENTITY, fetcher)

      const response = await handleShareRequest({
        sessionId: 'sess-1',
        sourcePath: 'reports/report.md',
      }, client, fixture.sessions, fixture.workspaces, {
        mode: 'nas',
        artifactRoot: fixture.artifactRoot,
      })

      expect(response).toMatchObject({ ok: false, error: { code: 'bad-request' } })
      expect(fetcher).toHaveBeenCalledOnce()
      await expect(access(join(fixture.root, 'escaped.md'))).rejects.toThrow()
    } finally {
      await fixture.cleanup()
    }
  })
})

describe('resolveShareStorage', () => {
  it('requires an absolute DSH-side artifact root only in NAS mode', () => {
    expect(resolveShareStorage({ mode: 'local', serviceUrl: 'http://hub' })).toEqual({ mode: 'local' })
    expect(() => resolveShareStorage({ mode: 'nas', serviceUrl: 'http://hub' })).toThrow('artifactRoot is required')
    expect(() => resolveShareStorage({
      mode: 'nas', serviceUrl: 'http://hub', artifactRoot: 'relative/path',
    })).toThrow('artifactRoot must be absolute')
    expect(resolveShareStorage({
      mode: 'nas', serviceUrl: 'http://hub', artifactRoot: '/mnt/dsh-nas',
    })).toEqual({ mode: 'nas', artifactRoot: '/mnt/dsh-nas' })
  })
})

async function createFixture() {
  const root = await mkdtemp(join(tmpdir(), 'dsh-artifact-hub-nas-'))
  const workspace = join(root, 'workspace')
  const artifactRoot = join(root, 'dsh-nas-mount')
  await mkdir(join(workspace, 'reports'), { recursive: true })
  await mkdir(artifactRoot)
  return {
    root,
    workspace,
    artifactRoot,
    sessions: {
      get: (sessionId: string) => sessionId === 'sess-1'
        ? { header: { cwd: workspace } }
        : undefined,
    },
    workspaces: {
      list: () => [{
        id: 'workspace-1', path: workspace, title: 'Project One', sessionIds: ['sess-1'],
      }],
    },
    cleanup: async () => rm(root, { recursive: true, force: true }),
  }
}
