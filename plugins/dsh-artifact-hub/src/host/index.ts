import type { Context } from '@deepseek-ai/cordis'
import Schema from '@deepseek-ai/schemastery'
import { isAbsolute } from 'node:path'
import { ArtifactHubClient } from './client.ts'
import {
  registerShareRoute,
  type HostConnectionRpc,
  type HostSessionStore,
  type HostWorkspaceRegistry,
  type ShareStorage,
} from './route.ts'

export { ArtifactHubClient, ArtifactHubRequestError } from './client.ts'
export {
  handleCreatedSharesRequest,
  handleShareRequest,
  handleLocalShareRequest,
  registerShareRoute,
  registerLocalShareRoute,
} from './route.ts'
export { copyNasSnapshot, createNasShare, type NasCopyRequest } from './nas.ts'
export * from '../contracts.ts'

export const name = 'artifact-hub-local-share'
export const inject = ['connection', 'sessions', 'workspaceRegistry']

/** Artifact Hub connection, storage mode, and trusted identity settings. */
export interface Config {
  readonly mode: 'local' | 'nas'
  readonly serviceUrl: string
  /** DSH-side mount path. Required in NAS mode; it may differ from the Hub path. */
  readonly artifactRoot?: string
  /** @deprecated Use createdById. */
  readonly createdBy?: string
  readonly createdById?: string
  readonly createdByName?: string
}

/** Validate Artifact Hub settings when the plugin loads. */
export const Config: Schema<Config> = Schema.object({
  mode: Schema.union(['local', 'nas']).default('local'),
  serviceUrl: Schema.string().default('http://127.0.0.1:8000'),
  artifactRoot: Schema.string(),
  createdBy: Schema.string(),
  createdById: Schema.string(),
  createdByName: Schema.string(),
})

interface HostContext extends Context {
  readonly connection: {
    readonly rpc: HostConnectionRpc
  }
  readonly sessions: HostSessionStore
  readonly workspaceRegistry: HostWorkspaceRegistry
}

/** Register the loopback-only browser RPC backed by the selected storage mode. */
export function apply(ctx: Context, config: Config): void {
  const createdById = config.createdById?.trim()
    || config.createdBy?.trim()
    || 'dsh-local-user'
  const createdByName = config.createdByName?.trim() || createdById
  if (createdById.length > 128) throw new Error('createdById must not exceed 128 characters')
  if (createdByName.length > 128) throw new Error('createdByName must not exceed 128 characters')
  const host = ctx as HostContext
  const client = new ArtifactHubClient(config.serviceUrl, {
    createdById,
    createdByName,
  })
  const storage = resolveShareStorage(config)
  registerShareRoute(
    host.connection.rpc,
    client,
    host.sessions,
    host.workspaceRegistry,
    storage,
  )
}

/** Resolve and validate the DSH-side storage settings before serving requests. */
export function resolveShareStorage(config: Config): ShareStorage {
  if (config.mode === 'local') return { mode: 'local' }
  const artifactRoot = config.artifactRoot?.trim()
  if (artifactRoot === undefined || artifactRoot === '') {
    throw new Error('artifactRoot is required in NAS mode')
  }
  if (!isAbsolute(artifactRoot)) throw new Error('artifactRoot must be absolute in NAS mode')
  return { mode: 'nas', artifactRoot }
}
