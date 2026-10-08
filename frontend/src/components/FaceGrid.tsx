import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'
import { api, faceUrl, formatDate, personLabel } from '../api'
import type { FaceItem, Person } from '../api'

interface Props {
  faces: FaceItem[]
  people: Person[]
  /** The person these faces currently belong to (enables "Not this person"). */
  current?: Person
  onChanged: () => void
}

/** Selectable grid of face crops with move / split actions. */
export default function FaceGrid({ faces, people, current, onChanged }: Props) {
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  async function apply(target: { person_id?: number | null; new_person_name?: string }) {
    setBusy(true)
    setError(null)
    try {
      await api.assignFaces([...selected], target)
      setSelected(new Set())
      onChanged()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const others = people.filter((p) => p.id !== current?.id)

  return (
    <div>
      <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-2">
        {faces.map((f) => {
          const on = selected.has(f.id)
          return (
            <button
              key={f.id}
              onClick={() => toggle(f.id)}
              title={`${f.filename}\n${formatDate(f.taken_at)}${f.similarity != null ? `\nmatch ${Math.round(f.similarity * 100)}%` : ''}`}
              className={`relative aspect-square overflow-hidden rounded-full ring-offset-2 ring-offset-stone-50 transition ${
                on ? 'ring-4 ring-amber-500 scale-95' : 'hover:ring-2 hover:ring-stone-300'
              }`}
            >
              <img src={faceUrl(f.id)} alt="" loading="lazy" className="h-full w-full object-cover" />
              {f.similarity != null && f.similarity < 0.45 && (
                <span className="absolute inset-x-0 bottom-0 bg-amber-600/85 text-[9px] text-white">check</span>
              )}
            </button>
          )
        })}
      </div>

      <AnimatePresence>
        {selected.size > 0 && (
          <motion.div
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            className="fixed bottom-4 inset-x-4 z-30 mx-auto max-w-3xl rounded-2xl bg-stone-900 text-stone-100 shadow-2xl p-3 flex flex-wrap items-center gap-2"
          >
            <span className="px-2 text-sm">{selected.size} selected</span>
            {current && (
              <button
                disabled={busy}
                onClick={() => apply({ person_id: null })}
                className="rounded-lg bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20"
              >
                Not {personLabel(current)}
              </button>
            )}
            <select
              disabled={busy}
              value=""
              onChange={(e) => e.target.value && apply({ person_id: Number(e.target.value) })}
              className="rounded-lg bg-white/10 px-3 py-1.5 text-sm text-stone-100 [&>option]:text-stone-900"
            >
              <option value="">Move to…</option>
              {others.map((p) => (
                <option key={p.id} value={p.id}>
                  {personLabel(p)}
                </option>
              ))}
            </select>
            <button
              disabled={busy}
              onClick={() => {
                const name = window.prompt('Name for the new person (leave empty for now):')
                if (name !== null) apply({ new_person_name: name })
              }}
              className="rounded-lg bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20"
            >
              New person…
            </button>
            <button onClick={() => setSelected(new Set())} className="ml-auto px-3 py-1.5 text-sm text-stone-400 hover:text-white">
              Clear
            </button>
            {error && <p className="w-full px-2 text-sm text-rose-300">{error}</p>}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
