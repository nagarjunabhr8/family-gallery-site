import { createHash } from 'node:crypto'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'

/** rel path -> "size|mtimeMs|sha256" for every file under root (hidden files included). */
export type Snapshot = Record<string, string>

export function snapshot(root: string): Snapshot {
  const out: Snapshot = {}
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name)
      if (entry.isDirectory()) walk(full)
      else if (entry.isFile()) {
        const st = statSync(full, { bigint: true })
        const sha = createHash('sha256').update(readFileSync(full)).digest('hex')
        out[relative(root, full).split(sep).join('/')] = `${st.size}|${st.mtimeNs}|${sha}`
      }
    }
  }
  walk(root)
  return out
}

/** Human-readable differences between two snapshots (empty = identical). */
export function diff(before: Snapshot, after: Snapshot): string[] {
  const problems: string[] = []
  for (const k of Object.keys(before)) {
    if (!(k in after)) problems.push(`REMOVED ${k}`)
    else if (before[k] !== after[k]) problems.push(`CHANGED ${k}`)
  }
  for (const k of Object.keys(after)) if (!(k in before)) problems.push(`ADDED ${k}`)
  return problems.sort()
}
