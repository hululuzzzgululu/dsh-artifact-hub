import type { Context } from '@deepseek-ai/cordis'
import { ArtifactHubWorkspace, type ArtifactHubWorkspaceProps } from './ArtifactHubWorkspace.tsx'
import { ArtifactFiles, type ArtifactFilesProps } from './ArtifactFiles.tsx'
import { requestCreatedShares, requestLocalShare, type ClientConnectionRpc } from './api.ts'
import { producedFiles, type TurnTailOwner } from './deliverables.ts'
import { en, NS, zh, type ArtifactHubTranslate } from './locales.ts'
import { mountArtifactHubSidebarEntry } from './sidebar-entry.ts'
import { ArtifactHubWorkspaceController } from './workspace-controller.ts'

export { requestCreatedShares, requestLocalShare } from './api.ts'
export { ArtifactHubWorkspace } from './ArtifactHubWorkspace.tsx'
export { ArtifactFiles } from './ArtifactFiles.tsx'
export { producedFiles } from './deliverables.ts'
export { ArtifactHubWorkspaceController } from './workspace-controller.ts'
export * from '../contracts.ts'

export const name = 'artifact-hub-local-share-client'
export const inject = ['slots', 'locale', 'connection']

interface ClientContext extends Context {
  readonly connection: {
    readonly rpc: ClientConnectionRpc
  }
  readonly locale: {
    register(namespace: string, dictionaries: Readonly<Record<string, Readonly<Record<string, string>>>>): () => void
    bind(namespace: string): ArtifactHubTranslate
    subscribe(listener: () => void): () => void
  }
  readonly slots: {
    inject(name: string, register: () => unknown): unknown
    register(
      options: {
        readonly name: string
        readonly priority: number
        readonly locale: string
        readonly select: (owner: TurnTailOwner) => readonly string[] | null
      },
      component: (props: ArtifactFilesProps) => React.ReactNode,
    ): unknown
    register(
      options: {
        readonly name: 'shell.overlay'
        readonly id: string
        readonly order?: number
        readonly label?: string | (() => string)
        readonly locale?: string
        readonly inject: () => ArtifactHubWorkspaceProps
      },
      component: (props: ArtifactHubWorkspaceProps) => React.ReactNode,
    ): unknown
  }
}

/** Register localized Artifact Hub controls ahead of the standard deliverables row. */
export function apply(ctx: Context): void {
  const client = ctx as ClientContext
  const requestShare = (request: Parameters<typeof requestLocalShare>[0], signal?: AbortSignal) =>
    requestLocalShare(request, client.connection.rpc, signal)
  const requestShares = (signal?: AbortSignal) => requestCreatedShares(client.connection.rpc, signal)
  const controller = new ArtifactHubWorkspaceController()
  const t = client.locale.bind(NS)
  ctx.effect(() => client.locale.register(NS, { zh, en }), 'artifact-hub: browser dictionaries')
  client.slots.inject('conversation.chat.turnTail', () => client.slots.register({
    name: 'conversation.chat.turnTail',
    priority: -10,
    locale: NS,
    select: producedFiles,
  }, props => <ArtifactFiles {...props} requestShare={requestShare} requestShares={requestShares} />))
  client.slots.inject('shell.overlay', () => client.slots.register({
    name: 'shell.overlay',
    id: 'artifact-hub-share-center',
    order: 40,
    label: () => t('center.label'),
    locale: NS,
    inject: () => ({ controller, requestShares, t }),
  }, ArtifactHubWorkspace))
  ctx.effect(
    () => typeof window === 'undefined' || typeof document === 'undefined'
      ? () => {}
      : mountArtifactHubSidebarEntry(controller, t, listener => client.locale.subscribe(listener)),
    'artifact-hub: share center sidebar entry',
  )
}
