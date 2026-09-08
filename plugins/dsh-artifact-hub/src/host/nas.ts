import { createHash, randomUUID } from 'node:crypto'
import { createReadStream, createWriteStream } from 'node:fs'
import { mkdir, realpath, rename, stat, unlink } from 'node:fs/promises'
import { basename, dirname, isAbsolute, relative, resolve, sep } from 'node:path'
import { Transform, type TransformCallback } from 'node:stream'
import { pipeline } from 'node:stream/promises'
import { ArtifactHubClient, type TrustedLocalShareRequest } from './client.ts'
import type { LocalShareResult } from '../contracts.ts'

/** Execute the Hub reservation, DSH-to-NAS copy, and Hub commit protocol. */
export async function createNasShare(
  client: ArtifactHubClient,
  request: TrustedLocalShareRequest,
  artifactRoot: string,
  signal?: AbortSignal,
): Promise<LocalShareResult> {
  await Promise.all([
    resolveSourceFile(request.workspaceRoot, request.sourcePath),
    resolveArtifactRoot(artifactRoot),
  ])
  signal?.throwIfAborted()
  const prepared = await client.prepareNasShare(request, signal)
  const checksum = await copyNasSnapshot({
    workspaceRoot: request.workspaceRoot,
    sourcePath: request.sourcePath,
    artifactRoot,
    storageKey: prepared.storageKey,
  }, signal)
  return client.commitNasShare({
    uploadId: prepared.uploadId,
    checksum,
    ...(request.expiresAt === undefined ? {} : { expiresAt: request.expiresAt }),
  }, signal)
}

export interface NasCopyRequest {
  readonly workspaceRoot: string
  readonly sourcePath: string
  readonly artifactRoot: string
  readonly storageKey: string
}

/** Copy one immutable snapshot inside the DSH host without an HTTP byte upload. */
export async function copyNasSnapshot(
  request: NasCopyRequest,
  signal?: AbortSignal,
): Promise<string> {
  signal?.throwIfAborted()
  const source = await resolveSourceFile(request.workspaceRoot, request.sourcePath)
  const artifactRoot = await resolveArtifactRoot(request.artifactRoot)
  const target = await resolveTargetFile(artifactRoot, request.storageKey)
  const temporary = resolve(dirname(target), `.${basename(target)}.${randomUUID()}.tmp`)
  const digest = createHash('sha256')
  const hasher = new Transform({
    transform(chunk: Buffer, _encoding: BufferEncoding, callback: TransformCallback): void {
      digest.update(chunk)
      callback(null, chunk)
    },
  })

  try {
    const input = createReadStream(source)
    const output = createWriteStream(temporary, { flags: 'wx' })
    if (signal === undefined) {
      await pipeline(input, hasher, output)
    } else {
      await pipeline(input, hasher, output, { signal })
    }
    await rename(temporary, target)
    return digest.digest('hex')
  } finally {
    await unlink(temporary).catch((error: unknown) => {
      if (!isErrno(error, 'ENOENT')) throw error
    })
  }
}

async function resolveSourceFile(workspaceRoot: string, sourcePath: string): Promise<string> {
  if (!isAbsolute(workspaceRoot)) throw new Error('Session workspace path must be absolute')
  assertSafeRelativePath(sourcePath, 'sourcePath')
  let realWorkspace: string
  let source: string
  try {
    realWorkspace = await realpath(workspaceRoot)
    const candidate = resolve(realWorkspace, sourcePath)
    assertInside(candidate, realWorkspace, 'sourcePath')
    source = await realpath(candidate)
  } catch (error: unknown) {
    if (isErrno(error, 'ENOENT')) throw new Error('source Session File does not exist')
    throw error
  }
  assertInside(source, realWorkspace, 'sourcePath')
  if (!(await stat(source)).isFile()) throw new Error('source Session File does not exist')
  return source
}

async function resolveArtifactRoot(configuredRoot: string): Promise<string> {
  if (!isAbsolute(configuredRoot)) throw new Error('artifactRoot must be absolute in NAS mode')
  let root: string
  try {
    root = await realpath(configuredRoot)
  } catch (error: unknown) {
    if (isErrno(error, 'ENOENT')) throw new Error('NAS artifactRoot does not exist')
    throw error
  }
  if (!(await stat(root)).isDirectory()) throw new Error('NAS artifactRoot must be a directory')
  return root
}

async function resolveTargetFile(artifactRoot: string, storageKey: string): Promise<string> {
  assertSafeRelativePath(storageKey, 'storageKey')
  const candidate = resolve(artifactRoot, storageKey)
  assertInside(candidate, artifactRoot, 'storageKey')
  await mkdir(dirname(candidate), { recursive: true })
  const realParent = await realpath(dirname(candidate))
  assertInside(realParent, artifactRoot, 'storageKey')
  return resolve(realParent, basename(candidate))
}

function assertSafeRelativePath(value: string, label: string): void {
  if (value.trim() === ''
    || isAbsolute(value)
    || value.startsWith('/')
    || value.startsWith('\\')
    || /^[A-Za-z]:[\\/]/u.test(value)
    || value.split(/[\\/]+/u).includes('..')) {
    throw new Error(`${label} must be a safe relative path`)
  }
}

function assertInside(candidate: string, root: string, label: string): void {
  const pathFromRoot = relative(root, candidate)
  if (pathFromRoot === '..' || pathFromRoot.startsWith(`..${sep}`) || isAbsolute(pathFromRoot)) {
    throw new Error(`${label} escapes its configured root`)
  }
}

function isErrno(error: unknown, code: string): error is NodeJS.ErrnoException {
  return error instanceof Error && 'code' in error && error.code === code
}
