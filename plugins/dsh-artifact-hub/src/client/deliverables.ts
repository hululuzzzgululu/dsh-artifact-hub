/** Minimal produced-file record published by DSH's deliverables plugin. */
interface ProducedPath {
  readonly seq: number
  readonly path: string
}

interface DeliverablesData {
  readonly produced: readonly ProducedPath[]
}

/** Structural turn-tail owner fields consumed by the Artifact Hub row. */
export interface TurnTailOwner {
  readonly seq: number
  readonly turn: {
    readonly data: {
      get(key: string): unknown
    }
  }
  readonly openFile: (path: string) => void
}

/** Return valid, de-duplicated produced files settled before the closing response. */
export function producedFiles(owner: TurnTailOwner): readonly string[] | null {
  const value = owner.turn.data.get('deliverables')
  if (!isDeliverablesData(value)) return null
  const paths: string[] = []
  const seen = new Set<string>()
  for (const produced of value.produced) {
    if (produced.seq > owner.seq || seen.has(produced.path)) continue
    seen.add(produced.path)
    paths.push(produced.path)
  }
  return paths.length === 0 ? null : paths
}

function isDeliverablesData(value: unknown): value is DeliverablesData {
  return isRecord(value) && Array.isArray(value.produced) && value.produced.every(item =>
    isRecord(item)
    && typeof item.seq === 'number'
    && Number.isFinite(item.seq)
    && typeof item.path === 'string'
    && item.path.trim() !== '')
}

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
