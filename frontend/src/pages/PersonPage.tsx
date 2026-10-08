import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, faceUrl, formatDate, personLabel, thumbUrl, yearSpan } from '../api'
import type { FaceItem, Person, PersonDetail } from '../api'
import FaceGrid from '../components/FaceGrid'
import Viewer from '../components/Viewer'
import { rotationStyle } from '../components/Photo'

export default function PersonPage({ id }: { id: number }) {
  const [person, setPerson] = useState<PersonDetail | null>(null)
  const [people, setPeople] = useState<Person[]>([])
  const [faces, setFaces] = useState<FaceItem[] | null>(null)
  const [tab, setTab] = useState<'photos' | 'faces'>('photos')
  const [open, setOpen] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.person(id).then(setPerson).catch((e) => setError(e.message))
    api.people(true).then((d) => setPeople(d.people))
    api.personFaces(id).then(setFaces).catch(() => setFaces([]))
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const years = useMemo(() => {
    const out: { year: number; photos: PersonDetail['photos'] }[] = []
    for (const ph of person?.photos ?? []) {
      const y = new Date(ph.taken_at).getFullYear()
      if (!out.length || out[out.length - 1].year !== y) out.push({ year: y, photos: [] })
      out[out.length - 1].photos.push(ph)
    }
    return out
  }, [person])

  if (error) return <p className="text-rose-700">{error}</p>
  if (!person) return null

  async function save(patch: Parameters<typeof api.updatePerson>[1]) {
    try {
      await api.updatePerson(person!.id, patch)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function mergeInto(targetId: number) {
    const target = people.find((p) => p.id === targetId)
    if (!target || !window.confirm(`Merge ${personLabel(person!)} into ${personLabel(target)}? All faces move over.`)) return
    await api.mergePerson(person!.id, targetId)
    window.location.hash = `#/people/${targetId}`
  }

  return (
    <div>
      <a href="#/people" className="text-sm text-stone-500 hover:text-stone-800">
        ← People
      </a>
      <header className="mt-4 flex flex-col sm:flex-row gap-6 sm:items-center">
        <div className="h-28 w-28 shrink-0 overflow-hidden rounded-full bg-stone-200 shadow-md">
          {person.cover_face_id && <img src={faceUrl(person.cover_face_id)} alt="" className="h-full w-full object-cover" />}
        </div>
        <div className="flex-1 min-w-0">
          <input
            key={`name-${person.id}-${person.name}`}
            defaultValue={person.name ?? ''}
            placeholder="Add a name"
            onBlur={(e) => e.target.value.trim() !== (person.name ?? '') && save({ name: e.target.value })}
            onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
            className="w-full bg-transparent font-serif text-4xl text-stone-900 outline-none placeholder:text-stone-300 focus:border-b focus:border-stone-300"
          />
          <p className="mt-1 text-sm text-stone-500">
            {person.photo_count} photos{person.first_taken && ` · ${yearSpan(person.first_taken, person.last_taken)}`}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2 text-stone-600">
              Born
              <input
                type="date"
                key={`birth-${person.birth_date}`}
                defaultValue={person.birth_date ?? ''}
                onChange={(e) => save({ birth_date: e.target.value || null })}
                className="rounded-lg border border-stone-300 bg-paper px-2 py-1"
              />
            </label>
            <button
              onClick={() => save({ hidden: !person.hidden })}
              className="rounded-lg border border-stone-300 px-3 py-1 hover:bg-stone-100"
              title="Hidden people (strangers, statues) don't appear in the People list"
            >
              {person.hidden ? 'Unhide' : 'Hide (not family)'}
            </button>
            <select
              value=""
              onChange={(e) => e.target.value && mergeInto(Number(e.target.value))}
              className="rounded-lg border border-stone-300 bg-paper px-2 py-1"
            >
              <option value="">Same person as…</option>
              {people
                .filter((p) => p.id !== person.id)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {personLabel(p)}
                  </option>
                ))}
            </select>
          </div>
        </div>
      </header>

      <div className="mt-8 flex gap-1 border-b border-stone-200">
        {(['photos', 'faces'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm ${
              tab === t ? 'border-amber-600 text-stone-900' : 'border-transparent text-stone-500 hover:text-stone-800'
            }`}
          >
            {t === 'photos' ? 'Photos through the years' : `Review faces (${faces?.length ?? '…'})`}
          </button>
        ))}
      </div>

      {tab === 'photos' ? (
        <div className="mt-6 space-y-10">
          {!person.birth_date && person.photos.length > 0 && (
            <p className="text-sm text-stone-500">Add a birth date above to see {person.name ?? 'their'} age in every photo.</p>
          )}
          {years.map((y) => (
            <section key={y.year}>
              <h2 className="font-serif text-2xl text-stone-800">{y.year}</h2>
              <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                {y.photos.map((ph) => (
                  <button
                    key={ph.id}
                    onClick={() => setOpen(person.photos.indexOf(ph))}
                    className="group text-left"
                  >
                    <div className="relative aspect-square overflow-hidden rounded-xl bg-stone-200">
                      {ph.has_thumb && (
                        <img
                          src={thumbUrl(ph.id)}
                          alt={ph.filename}
                          loading="lazy"
                          style={rotationStyle(ph.rotation)}
                          className="h-full w-full object-cover transition group-hover:scale-105"
                        />
                      )}
                      {ph.age && (
                        <span className="absolute bottom-2 left-2 rounded-full bg-white/90 px-2.5 py-0.5 font-serif text-sm text-stone-800 shadow">
                          {ph.age}
                        </span>
                      )}
                    </div>
                    <p className="mt-1.5 text-xs text-stone-500">{formatDate(ph.taken_at)}</p>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : (
        <div className="mt-6 pb-24">
          <p className="mb-4 text-sm text-stone-500">
            Least certain matches are shown first. Select any faces that aren't {personLabel(person)} and fix them.
          </p>
          {faces && <FaceGrid faces={faces} people={people} current={person} onChanged={load} />}
        </div>
      )}

      {open !== null && (
        <Viewer items={person.photos} index={open} onIndex={setOpen} onClose={() => setOpen(null)} />
      )}
    </div>
  )
}
