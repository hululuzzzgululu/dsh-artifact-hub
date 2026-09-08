import type { ArtifactHubTranslate } from './locales.ts'
import type { ArtifactHubWorkspaceController } from './workspace-controller.ts'

export const ARTIFACT_HUB_ENTRY_SELECTOR = '[data-artifact-hub-sidebar-entry]'

const FAMILY_SELECTOR = [
  '[data-dsh-taskboard-entry]',
  '[data-dsh-ssh-entry]',
  '[data-dsh-mnemon-entry]',
  ARTIFACT_HUB_ENTRY_SELECTOR,
].join(', ')
const ACTIVE_ATTR = 'data-artifact-hub-active'
const PEER_ACTIVE_ATTRS = [
  'data-dsh-taskboard-active',
  'data-dsh-ssh-active',
  'data-dsh-mnemon-active',
]
const ACTIVATE_EVENT = 'dsh-panel-activate'
const CONTEXT_SELECTOR = [
  '[data-dsh-taskboard-entry]',
  '[data-dsh-ssh-entry]',
  '[data-dsh-mnemon-entry]',
  '[class*="sessionRow"]',
  '[class*="projectRow"]',
  '[class*="searchResultRow"]',
  '[class*="newSession"]',
].join(', ')

function sidebarRoot(): HTMLElement | undefined {
  const column = document.querySelector<HTMLElement>(
    '[data-pane="sidebar"], [class*="sidebarCol"], .dshDesktopUpstreamSidebar',
  )
  if (column === null) return undefined
  return column.querySelector<HTMLElement>('[class*="logoRow"]')?.parentElement
    ?? (column.firstElementChild as HTMLElement | undefined)
}

function newSessionButton(root: HTMLElement): HTMLButtonElement | undefined {
  const nested = root.querySelector<HTMLButtonElement>('button[class*="newSession"]')
  if (nested !== null) return nested
  for (const child of root.children) {
    if (child.tagName === 'BUTTON') return child as HTMLButtonElement
  }
  return undefined
}

function createIcon(): SVGSVGElement {
  const namespace = 'http://www.w3.org/2000/svg'
  const icon = document.createElementNS(namespace, 'svg')
  icon.setAttribute('viewBox', '0 0 20 20')
  icon.setAttribute('width', '20')
  icon.setAttribute('height', '20')
  icon.setAttribute('fill', 'none')
  icon.setAttribute('stroke', 'currentColor')
  icon.setAttribute('stroke-width', '1.5')
  icon.setAttribute('stroke-linecap', 'round')
  icon.setAttribute('stroke-linejoin', 'round')
  icon.setAttribute('aria-hidden', 'true')
  const path = document.createElementNS(namespace, 'path')
  path.setAttribute('d', 'M4 5.5h12v10H4zM7 5.5V3.75h6V5.5M7 9h6M7 12h4')
  icon.append(path)
  return icon
}

function createEntry(controller: ArtifactHubWorkspaceController): {
  entry: HTMLButtonElement
  label: HTMLSpanElement
} {
  const entry = document.createElement('button')
  entry.type = 'button'
  entry.dataset.artifactHubSidebarEntry = ''
  const icon = document.createElement('span')
  icon.dataset.artifactHubEntryIcon = ''
  icon.append(createIcon())
  const label = document.createElement('span')
  label.dataset.artifactHubEntryLabel = ''
  entry.append(icon, label)
  entry.addEventListener('click', () => { controller.open() })
  return { entry, label }
}

function placeEntry(root: HTMLElement, entry: HTMLButtonElement): boolean {
  const button = newSessionButton(root)
  if (button === undefined) return false
  const row = button.closest('[class*="logoRow"]')
  const base = row !== null && row.parentElement === root ? row : button
  const parent = base.parentElement ?? root
  if (entry.parentElement === parent) return true
  const family = Array.from(parent.children).filter(
    (element): element is HTMLElement => element instanceof HTMLElement && element.matches(FAMILY_SELECTOR),
  )
  const anchor = family.at(-1)?.nextElementSibling ?? base.nextElementSibling
  parent.insertBefore(entry, anchor !== null && anchor.parentElement === parent ? anchor : null)
  return true
}

function installStyles(): () => void {
  const style = document.createElement('style')
  style.dataset.artifactHubSidebarStyle = ''
  style.textContent = `
    ${ARTIFACT_HUB_ENTRY_SELECTOR} {
      box-sizing: border-box; display: flex; width: 100%; min-height: 36px;
      align-items: center; gap: 10px; border: none; border-radius: 8px;
      padding: 0 10px; color: var(--dsw-alias-label-secondary, #646a73);
      background: transparent; font: inherit; font-size: 13px; white-space: nowrap;
      cursor: pointer;
    }
    ${ARTIFACT_HUB_ENTRY_SELECTOR}:hover {
      color: var(--dsw-alias-label-primary, #1f2329);
      background: var(--dsw-alias-interactive-bg-hover, rgba(31,35,41,.08));
    }
    ${ARTIFACT_HUB_ENTRY_SELECTOR}[data-active] {
      color: var(--dsw-alias-label-primary, #1f2329);
      background: var(--dsw-alias-interactive-bg-active, rgba(31,35,41,.10));
      font-weight: 600;
    }
    ${ARTIFACT_HUB_ENTRY_SELECTOR} [data-artifact-hub-entry-icon] {
      display: inline-flex; flex: none; align-items: center; justify-content: center;
      width: 24px; height: 24px;
    }
    ${ARTIFACT_HUB_ENTRY_SELECTOR} [data-artifact-hub-entry-label] {
      overflow: hidden; text-overflow: ellipsis;
    }
    [data-sidebar-collapsed] ${ARTIFACT_HUB_ENTRY_SELECTOR} {
      width: 36px; min-height: 36px; justify-content: center; margin: 0 auto 12px;
      padding: 0; border-radius: 50%; color: var(--dsw-alias-label-primary, #1f2329);
    }
    [data-sidebar-collapsed] ${ARTIFACT_HUB_ENTRY_SELECTOR} [data-artifact-hub-entry-label] {
      display: none;
    }
  `
  document.head.append(style)
  return () => { style.remove() }
}

/** Mount a self-healing, native-style Share Center row under New Session. */
export function mountArtifactHubSidebarEntry(
  controller: ArtifactHubWorkspaceController,
  t: ArtifactHubTranslate,
  subscribeLocale?: (listener: () => void) => () => void,
): () => void {
  const { entry, label } = createEntry(controller)
  const disposeStyles = installStyles()
  let root: HTMLElement | undefined
  let placed = false

  const syncLabel = (): void => {
    const text = t('center.label')
    if (entry.getAttribute('aria-label') !== text) entry.setAttribute('aria-label', text)
    if (entry.title !== text) entry.title = text
    if (label.textContent !== text) label.textContent = text
  }
  const tryPlace = (): void => {
    syncLabel()
    if (root !== undefined && !root.isConnected) {
      rootObserver.disconnect()
      root = undefined
      placed = false
    }
    if (placed && document.body.contains(entry)) return
    root ??= sidebarRoot()
    if (root === undefined) return
    placed = placeEntry(root, entry)
    if (placed) rootObserver.observe(root, { childList: true, subtree: true })
  }
  const rootObserver = new MutationObserver(() => {
    if (root === undefined || !root.isConnected || !root.contains(entry)) {
      placed = false
      tryPlace()
    }
  })
  const waitObserver = new MutationObserver(tryPlace)
  waitObserver.observe(document.body, { childList: true, subtree: true })

  const syncActive = (): void => {
    const active = controller.getSnapshot().open
    entry.toggleAttribute('data-active', active)
    if (!active) {
      document.documentElement.removeAttribute(ACTIVE_ATTR)
      return
    }
    for (const attribute of PEER_ACTIVE_ATTRS) document.documentElement.removeAttribute(attribute)
    document.documentElement.setAttribute(ACTIVE_ATTR, '')
    document.dispatchEvent(new CustomEvent(ACTIVATE_EVENT, { detail: 'artifact-hub' }))
  }
  const onActivate = (event: Event): void => {
    if (controller.getSnapshot().open
      && (event as CustomEvent<unknown>).detail !== 'artifact-hub') controller.close()
  }
  const onContext = (event: MouseEvent): void => {
    if (controller.getSnapshot().open
      && event.target instanceof Element
      && event.target.closest(CONTEXT_SELECTOR) !== null) controller.close()
  }
  const unsubscribe = controller.subscribe(syncActive)
  const unsubscribeLocale = subscribeLocale?.(syncLabel) ?? (() => {})
  document.addEventListener(ACTIVATE_EVENT, onActivate)
  document.addEventListener('click', onContext, true)
  syncActive()
  tryPlace()

  return () => {
    waitObserver.disconnect()
    rootObserver.disconnect()
    unsubscribe()
    unsubscribeLocale()
    document.removeEventListener(ACTIVATE_EVENT, onActivate)
    document.removeEventListener('click', onContext, true)
    document.documentElement.removeAttribute(ACTIVE_ATTR)
    entry.remove()
    disposeStyles()
  }
}
