export interface ArtifactHubWorkspaceSnapshot {
  readonly open: boolean
}

/** Framework-neutral navigation state shared by the sidebar entry and overlay. */
export class ArtifactHubWorkspaceController {
  private snapshot: ArtifactHubWorkspaceSnapshot = { open: false }
  private readonly listeners = new Set<() => void>()

  getSnapshot = (): ArtifactHubWorkspaceSnapshot => this.snapshot

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }

  open(): void { this.setOpen(true, true) }
  close(): void { this.setOpen(false) }

  private setOpen(open: boolean, reassert = false): void {
    if (this.snapshot.open === open && !reassert) return
    this.snapshot = { open }
    for (const listener of this.listeners) listener()
  }
}
