import { lstat, readdir, realpath, stat } from 'node:fs/promises'
import { isAbsolute, relative, resolve } from 'node:path'
import type { WorkspaceFileEntry, WorkspaceFilesResult } from '../contracts.ts'

/** Keep one browser listing bounded even when a workspace contains generated caches. */
export const MAX_WORKSPACE_FILE_ENTRIES = 500

/** List one workspace directory without exposing the Host's absolute path. */
export async function listWorkspaceFiles(
  workspaceRoot: string,
  directory = '',
  signal?: AbortSignal,
): Promise<WorkspaceFilesResult> {
  signal?.throwIfAborted()
  if (!isAbsolute(workspaceRoot)) throw new Error('Session workspace path must be absolute')

  const realWorkspace = await realpath(workspaceRoot)
  const normalizedDirectory = normalizeRelativePath(directory, 'directory')
  const candidate = resolve(realWorkspace, normalizedDirectory)
  assertInside(candidate, realWorkspace, 'directory')
  // Re-resolve the requested directory as well: a browser must not be able
  // to address a symlink inside the workspace that points outside its root.
  const realCandidate = await realpath(candidate)
  assertInside(realCandidate, realWorkspace, 'directory')
  const directoryInfo = await stat(realCandidate)
  if (!directoryInfo.isDirectory()) throw new Error('Workspace path is not a directory')

  const names = await readdir(realCandidate)
  const entries: WorkspaceFileEntry[] = []
  let scanned = 0
  for (const name of names.sort((left, right) => left.localeCompare(right))) {
    scanned += 1
    signal?.throwIfAborted()
    const child = resolve(realCandidate, name)
    // Do not follow symlinks in a browser-facing directory listing. The share
    // endpoint performs its own real-path check, but refusing links here keeps
    // the picker deterministic and prevents an entry from changing roots.
    const childInfo = await lstat(child).catch(() => undefined)
    if (childInfo === undefined || (!childInfo.isFile() && !childInfo.isDirectory())) continue
    const path = normalizedDirectory === '' ? name : `${normalizedDirectory}/${name}`
    entries.push(childInfo.isDirectory()
      ? { name, path, kind: 'directory' }
      : {
          name,
          path,
          kind: 'file',
          size: childInfo.size,
          modifiedAt: new Date(childInfo.mtimeMs).toISOString(),
        })
    if (entries.length >= MAX_WORKSPACE_FILE_ENTRIES) break
  }

  return {
    directory: normalizedDirectory,
    entries: entries.sort(compareEntries),
    truncated: scanned < names.length,
  }
}

/** Normalize a browser path while retaining workspace-relative semantics. */
export function normalizeRelativePath(value: string, label: string): string {
  const normalized = value.replace(/\\/gu, '/')
  if (normalized.startsWith('/') || /^[A-Za-z]:\//u.test(normalized)) {
    throw new Error(`${label} must be a safe relative path`)
  }
  const segments = normalized.split('/').filter(segment => segment !== '' && segment !== '.')
  if (segments.includes('..')) throw new Error(`${label} must be a safe relative path`)
  return segments.join('/')
}

function compareEntries(left: WorkspaceFileEntry, right: WorkspaceFileEntry): number {
  if (left.kind !== right.kind) return left.kind === 'directory' ? -1 : 1
  return left.name.localeCompare(right.name)
}

function assertInside(candidate: string, root: string, label: string): void {
  const relativePath = relative(root, candidate)
  if (relativePath === '' || (!relativePath.startsWith('..') && !isAbsolute(relativePath))) return
  throw new Error(`${label} escapes the workspace`)
}
