import { motion } from 'framer-motion'
import { useCallback, useEffect, useState } from 'react'
import { api, faceUrl, personLabel, yearSpan } from '../api'
import type { PeopleList, Person } from '../api'

export default function People() {
  const [data, setData] = useState<PeopleList | null>(null)
  const [showHidden, setShowHidden] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => api.people(showHidden).then(setData), [showHidden])
  useEffect(() => {
    load()
  }, [load])

  async function rename(p: Person, name: string) {
    await api.updatePerson(p.id, { name })
    load()
  }

  async function merge(intoId: number) {
    setBusy(true)
    try {
      for (const id of selected.filter((x) => x !== intoId)) await api.mergePerson(id, intoId)
      setSelected([])
      setNote('Merged.')
      await load()
    } catch (e) {
      setNote((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function recluster() {
    setBusy(true)
    try {
      const r = await api.recluster()
      setNote(`Re-sorted: ${r.new_people} unnamed groups, ${r.unassigned} faces left unsorted. Named people were not changed.`)
      await load()
    } catch (e) {
      setNote((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!data) return null
  const named = data.people.filter((p) => p.name)
  const unnamed = data.people.filter((p) => !p.name)
  const selPeople = data.people.filter((p) => selected.includes(p.id))

  return (
    <div>
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl text-stone-900">People</h1>
          <p className="mt-2 text-stone-600 max-w-2xl">
            Faces are recognised on this computer. Name the people you know. Select two or more to merge them, or open
            someone to fix mistakes.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {data.hidden_people > 0 && (
            <label className="flex items-center gap-2 rounded-full bg-stone-200/70 px-3 py-1 text-sm text-stone-600">
              <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} className="accent-amber-600" />
              Show hidden ({data.hidden_people})
            </label>
          )}
          <button
            onClick={recluster}
            disabled={busy}
            className="rounded-xl border border-stone-300 px-4 py-1.5 text-sm hover:bg-stone-100 disabled:opacity-40"
            title="Re-sort unnamed groups. Named people and your corrections are kept."
          >
            Re-sort unnamed faces
          </button>
        </div>
      </div>
      {note && <p className="mt-3 text-sm text-stone-600">{note}</p>}

      {data.people.length === 0 && (
        <p className="mt-16 text-center text-stone-500">
          No people yet. Run a scan; faces are found during analysis.
        </p>
      )}

      {named.length > 0 && <Section title="Family & friends" people={named} {...{ selected, setSelected, rename }} />}
      {unnamed.length > 0 && <Section title="Who is this?" people={unnamed} {...{ selected, setSelected, rename }} />}

      {data.unassigned_faces > 0 && (
        <a
          href="#/people/unsorted"
          className="mt-10 inline-flex items-center gap-2 rounded-xl border border-dashed border-stone-300 px-4 py-3 text-sm text-stone-600 hover:bg-stone-100"
        >
          {data.unassigned_faces} faces not recognised yet (statues, strangers, single appearances) →
        </a>
      )}

      {selected.length >= 2 && (
        <motion.div
          initial={{ y: 80, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="fixed bottom-4 inset-x-4 z-30 mx-auto max-w-3xl rounded-2xl bg-stone-900 text-stone-100 shadow-2xl p-3 flex flex-wrap items-center gap-2"
        >
          <span className="px-2 text-sm">Merge {selected.length} into:</span>
          {selPeople.map((p) => (
            <button
              key={p.id}
              disabled={busy}
              onClick={() => merge(p.id)}
              className="rounded-lg bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20"
            >
              {personLabel(p)}
            </button>
          ))}
          <button onClick={() => setSelected([])} className="ml-auto px-3 py-1.5 text-sm text-stone-400 hover:text-white">
            Cancel
          </button>
        </motion.div>
      )}
    </div>
  )
}

interface SectionProps {
  title: string
  people: Person[]
  selected: number[]
  setSelected: (fn: (prev: number[]) => number[]) => void
  rename: (p: Person, name: string) => void
}

function Section({ title, people, selected, setSelected, rename }: SectionProps) {
  return (
    <section className="mt-10">
      <h2 className="font-serif text-xl text-stone-800">{title}</h2>
      <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-6">
        {people.map((p) => (
          <PersonCard
            key={p.id}
            p={p}
            selected={selected.includes(p.id)}
            onSelect={() =>
              setSelected((prev) => (prev.includes(p.id) ? prev.filter((x) => x !== p.id) : [...prev, p.id]))
            }
            onRename={(name) => rename(p, name)}
          />
        ))}
      </div>
    </section>
  )
}

function PersonCard({
  p,
  selected,
  onSelect,
  onRename,
}: {
  p: Person
  selected: boolean
  onSelect: () => void
  onRename: (name: string) => void
}) {
  const [draft, setDraft] = useState('')
  return (
    <motion.div layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="group text-center">
      <div className="relative mx-auto w-32 sm:w-36">
        <a href={`#/people/${p.id}`} className="block">
          <div
            className={`aspect-square overflow-hidden rounded-full bg-stone-200 ring-offset-4 ring-offset-stone-50 transition ${
              selected ? 'ring-4 ring-amber-500' : 'group-hover:ring-2 group-hover:ring-stone-300'
            } ${p.hidden ? 'opacity-50' : ''}`}
          >
            {p.cover_face_id && (
              <img src={faceUrl(p.cover_face_id)} alt={personLabel(p)} loading="lazy" className="h-full w-full object-cover" />
            )}
          </div>
        </a>
        <input
          type="checkbox"
          checked={selected}
          onChange={onSelect}
          aria-label={`Select ${personLabel(p)}`}
          className={`absolute top-1 right-1 h-5 w-5 accent-amber-600 ${selected ? '' : 'opacity-0 group-hover:opacity-100'}`}
        />
      </div>
      {p.name ? (
        <a href={`#/people/${p.id}`} className="mt-3 block font-serif text-lg text-stone-900 hover:underline">
          {p.name}
        </a>
      ) : (
        <form
          className="mt-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (draft.trim()) onRename(draft.trim())
          }}
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a name"
            className="w-full rounded-lg border border-stone-300 bg-white px-2 py-1 text-center text-sm outline-none focus:border-stone-500"
          />
        </form>
      )}
      <p className="mt-1 text-xs text-stone-500">
        {p.photo_count} photo{p.photo_count === 1 ? '' : 's'}
        {p.first_taken && ` · ${yearSpan(p.first_taken, p.last_taken)}`}
      </p>
    </motion.div>
  )
}
