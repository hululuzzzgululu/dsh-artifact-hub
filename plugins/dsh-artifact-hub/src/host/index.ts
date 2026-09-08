import type { Context } from '@deepseek-ai/cordis'
import Schema from '@deepseek-ai/schemastery'
import { ArtifactHubClient } from './client.ts'
import {
  registerLocalShareRoute,
  type HostConnectionRpc,
  type HostSessionStore,
  type HostWorkspaceRegistry,
} from './route.ts'

export { ArtifactHubClient, ArtifactHubRequestError } from './client.ts'
export {
  handleCreatedSharesRequest,
  handleLocalShareRequest,
  registerLocalShareRoute,
} from './route.ts'
export * from '../contracts.ts'

export const name = 'artifact-hub-local-share'
export const inject = ['connection', 'sessions', 'workspaceRegistry']

/** Local-mode Artifact Hub connection and trusted identity settings. */
export interface Config {
  readonly mode: 'local'
  readonly serviceUrl: string
  /** @deprecated Use createdById. */
  readonly createdBy?: string
  readonly createdById?: string
  readonly createdByName?: string
}

/** Validate Local-mode settings when the plugin loads. */
export const Config: Schema<Config> = Schema.object({
  mode: Schema.union(['local']).default('local'),
  serviceUrl: Schema.string().default('http://127.0.0.1:8000'),
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

/** Register the loopback-only browser RPC backed by Artifact Hub Local mode. */
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
  registerLocalShareRoute(
    host.connection.rpc,
    client,
    host.sessions,
    host.workspaceRegistry,
  )
}
