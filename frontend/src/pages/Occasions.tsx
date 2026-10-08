import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, dayMonth, MONTHS, personLabel, thumbUrl } from '../api'
import type { EventLink, FamilyOccasion, FestivalDay, OccasionInput, Person } from '../api'

const KIND_LABEL: Record<FamilyOccasion['kind'], string> = {
  birthday: 'Birthday',
  anniversary: 'Anniversary',
  other: 'Other',
}

function fmtDay(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })
}

export default function Occasions() {
  const [occasions, setOccasions] = useState<FamilyOccasion[]>([])
  const [people, setPeople] = useState<Person[]>([])
  const [editing, setEditing] = useState<FamilyOccasion | 'new' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.occasions().then(setOccasions).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    load()
    api.people().then((d) => setPeople(d.people))
  }, [load])

  return (
    <div className="max-w-4xl mx-auto space-y-14 pb-16">
      <section>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-serif text-3xl text-stone-900">Family occasions</h1>
            <p className="mt-1 text-sm text-stone-500">
              Birthdays and anniversaries repeat every year. Events on these days are named after them.
            </p>
          </div>
          <button onClick={() => setEditing('new')} className="rounded-full bg-stone-800 px-4 py-1.5 text-sm text-stone-50 hover:bg-stone-700">
            + Add a date
          </button>
        </div>
        {error && <p className="mt-4 text-sm text-rose-700">{error}</p>}

        <ul className="mt-6 divide-y divide-stone-200 rounded-2xl border border-stone-200 bg-paper">
          {occasions.length === 0 && (
            <li className="px-5 py-8 text-center text-stone-500">
              No family dates yet. Add birthdays and anniversaries, or add birth dates on People pages.
            </li>
          )}
          {occasions.map((o) => (
            <OccasionRow key={`${o.source}-${o.id ?? o.person_id}`} occasion={o} onEdit={() => setEditing(o)} onChanged={load} />
          ))}
        </ul>
      </section>

      <Festivals />

      {editing && (
        <OccasionDialog
          occasion={editing === 'new' ? null : editing}
          people={people}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            load()
          }}
        />
      )}
    </div>
  )
}

function OccasionRow({ occasion: o, onEdit, onChanged }: { occasion: FamilyOccasion; onEdit: () => void; onChanged: () => void }) {
  const [years, setYears] = useState<{ year: number; events: EventLink[] }[] | null>(null)
  const [open, setOpen] = useState(false)
  const kind = o.source === 'person' ? 'person' : 'occasion'
  const key = String(o.source === 'person' ? o.person_id : o.id)

  function toggle() {
    if (!open && years === null) api.occasionYears(kind, key).then(setYears)
    setOpen(!open)
  }

  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="w-16 shrink-0 text-center">
          <p className="font-serif text-2xl leading-none text-stone-900">{o.day}</p>
          <p className="text-xs uppercase tracking-wide text-stone-500">{MONTHS[o.month - 1].slice(0, 3)}</p>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-stone-900">
            {o.name}
            {o.kind !== 'other' && <span className="text-stone-500"> · {KIND_LABEL[o.kind]}</span>}
          </p>
          <p className="text-xs text-stone-500">
            {o.year ? `Since ${o.year}` : 'Year not set'}
            {o.person_name && o.source === 'occasion' && ` · linked to ${o.person_name}`}
            {o.source === 'person' && ' · from People'}
          </p>
        </div>
        <button onClick={toggle} className="rounded-lg px-3 py-1 text-sm text-stone-600 hover:bg-stone-100">
          {open ? 'Hide years' : 'Every year →'}
        </button>
        {o.source === 'person' ? (
          <a href={`#/people/${o.person_id}`} className="rounded-lg px-3 py-1 text-sm text-stone-600 hover:bg-stone-100">
            Edit on People
          </a>
        ) : (
          <>
            <button onClick={onEdit} className="rounded-lg px-3 py-1 text-sm text-stone-600 hover:bg-stone-100">
              Edit
            </button>
            <button
              onClick={async () => {
                if (window.confirm(`Delete "${o.name}"? Photos are not affected.`)) {
                  await api.deleteOccasion(o.id!)
                  onChanged()
                }
              }}
              className="rounded-lg px-3 py-1 text-sm text-rose-700 hover:bg-rose-50"
            >
              Delete
            </button>
          </>
        )}
      </div>
      {open && <YearStrip years={years} empty="No photos on this day yet." />}
    </li>
  )
}

function YearStrip({ years, empty }: { years: { year: number; events: EventLink[] }[] | null; empty: string }) {
  if (years === null) return <p className="mt-3 text-sm text-stone-400">Loading…</p>
  if (years.length === 0) return <p className="mt-3 text-sm text-stone-500">{empty}</p>
  return (
    <div className="mt-4 flex gap-3 overflow-x-auto pb-2">
      {years.flatMap((y) =>
        y.events.map((e) => (
          <a key={`${y.year}-${e.id}`} href={`#/events/${e.id}`} className="group w-36 shrink-0">
            <div className="aspect-square overflow-hidden rounded-xl bg-stone-200">
              {e.hero_media_id && (
                <img src={thumbUrl(e.hero_media_id)} alt="" loading="lazy" className="h-full w-full object-cover transition group-hover:scale-105" />
              )}
            </div>
            <p className="mt-1 font-serif text-lg text-stone-900">{y.year}</p>
            <p className="truncate text-xs text-stone-500">{e.title}</p>
          </a>
        )),
      )}
    </div>
  )
}

function OccasionDialog({
  occasion,
  people,
  onClose,
  onSaved,
}: {
  occasion: FamilyOccasion | null
  people: Person[]
  onClose: () => void
  onSaved: () => void
}) {
  const [form, setForm] = useState<OccasionInput>(
    occasion
      ? { kind: occasion.kind, name: occasion.name, month: occasion.month, day: occasion.day, year: occasion.year, person_id: occasion.person_id }
      : { kind: 'birthday', name: '', month: 1, day: 1, year: null, person_id: null },
  )
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      if (occasion?.id) await api.editOccasion(occasion.id, form)
      else await api.addOccasion(form)
      onSaved()
    } catch (err) {
      setError((err as Error).message || 'Please check the date')
    }
  }

  const set = <K extends keyof OccasionInput>(k: K, v: OccasionInput[K]) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <form onSubmit={submit} onClick={(e) => e.stopPropagation()} className="w-full max-w-md rounded-2xl bg-stone-50 p-6 shadow-2xl space-y-4">
        <h2 className="font-serif text-2xl text-stone-900">{occasion ? 'Edit date' : 'Add a family date'}</h2>
        <div className="flex gap-2">
          {(Object.keys(KIND_LABEL) as FamilyOccasion['kind'][]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => set('kind', k)}
              className={`rounded-full px-3 py-1 text-sm ${form.kind === k ? 'bg-stone-800 text-stone-50' : 'bg-stone-200 text-stone-700'}`}
            >
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>
        <input
          required
          autoFocus
          value={form.name}
          onChange={(e) => set('name', e.target.value)}
          placeholder={form.kind === 'anniversary' ? 'e.g. Amma & Nanna' : form.kind === 'birthday' ? 'e.g. Aadhya' : 'e.g. Griha pravesam'}
          className="w-full rounded-xl border border-stone-300 bg-paper px-4 py-2.5 outline-none focus:border-stone-500"
        />
        <div className="grid grid-cols-3 gap-3 text-sm">
          <label className="text-stone-600">
            Day
            <input type="number" min={1} max={31} required value={form.day} onChange={(e) => set('day', Number(e.target.value))}
              className="mt-1 w-full rounded-lg border border-stone-300 bg-paper px-2 py-1.5" />
          </label>
          <label className="text-stone-600">
            Month
            <select value={form.month} onChange={(e) => set('month', Number(e.target.value))}
              className="mt-1 w-full rounded-lg border border-stone-300 bg-paper px-2 py-1.5">
              {MONTHS.map((m, i) => (
                <option key={m} value={i + 1}>{m}</option>
              ))}
            </select>
          </label>
          <label className="text-stone-600">
            Year <span className="text-stone-400">(optional)</span>
            <input type="number" min={1900} max={2100} value={form.year ?? ''}
              onChange={(e) => set('year', e.target.value ? Number(e.target.value) : null)}
              className="mt-1 w-full rounded-lg border border-stone-300 bg-paper px-2 py-1.5" />
          </label>
        </div>
        {form.kind === 'birthday' && (
          <label className="block text-sm text-stone-600">
            Person (optional)
            <select value={form.person_id ?? ''} onChange={(e) => set('person_id', e.target.value ? Number(e.target.value) : null)}
              className="mt-1 w-full rounded-lg border border-stone-300 bg-paper px-2 py-1.5">
              <option value="">Not linked</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>{personLabel(p)}</option>
              ))}
            </select>
          </label>
        )}
        <p className="text-xs text-stone-500">
          {form.year ? `Shown as e.g. “${form.kind === 'birthday' ? `${form.name || 'Name'}'s 5th birthday` : form.kind === 'anniversary' ? `${form.name || 'Name'}: 10th anniversary` : form.name}”` : 'Add the year to see which birthday/anniversary it was.'}
          {' '}Repeats every {dayMonth(form.month, form.day)}.
        </p>
        {error && <p className="text-sm text-rose-700">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-xl px-4 py-2 text-sm text-stone-600 hover:bg-stone-200">Cancel</button>
          <button className="rounded-xl bg-stone-800 px-5 py-2 text-sm text-stone-50 hover:bg-stone-700">Save</button>
        </div>
      </form>
    </div>
  )
}

function Festivals() {
  const thisYear = Math.min(new Date().getFullYear(), 2030)
  const [year, setYear] = useState(thisYear)
  const [data, setData] = useState<{ years: number[]; festivals: FestivalDay[] } | null>(null)
  const [openKey, setOpenKey] = useState<string | null>(null)
  const [history, setHistory] = useState<Record<string, { year: number; events: EventLink[] }[]>>({})
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.festivals(year).then(setData).catch((e) => setError(e.message))
  }, [year])

  useEffect(() => {
    load()
  }, [load])

  async function edit(f: FestivalDay, date: string) {
    if (!date || date === f.date) return
    try {
      await api.editFestival(f.id, date)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  function toggleHistory(key: string) {
    if (openKey === key) return setOpenKey(null)
    setOpenKey(key)
    if (!history[key]) api.occasionYears('festival', key).then((h) => setHistory((prev) => ({ ...prev, [key]: h })))
  }

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-serif text-3xl text-stone-900">Festivals</h2>
          <p className="mt-1 text-sm text-stone-500">
            Telugu calendar dates (Hyderabad). If your family celebrated on a different day, change it here.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setYear(year - 1)} disabled={!data || year <= (data.years[0] ?? year)}
            className="h-8 w-8 rounded-full bg-stone-200 hover:bg-stone-300 disabled:opacity-30">‹</button>
          <span className="w-14 text-center font-serif text-2xl">{year}</span>
          <button onClick={() => setYear(year + 1)} disabled={!data || year >= (data.years[data.years.length - 1] ?? year)}
            className="h-8 w-8 rounded-full bg-stone-200 hover:bg-stone-300 disabled:opacity-30">›</button>
        </div>
      </div>
      {error && <p className="mt-3 text-sm text-rose-700">{error}</p>}
      <ul className="mt-6 divide-y divide-stone-200 rounded-2xl border border-stone-200 bg-paper">
        {data?.festivals.map((f) => (
          <li key={f.id} className="px-5 py-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex-1 min-w-48">
                <p className="text-stone-900">{f.name}</p>
                <p className="text-xs text-stone-500">
                  {fmtDay(f.date)}
                  {f.start !== f.end && ` · ${f.note ?? 'festival days'}: ${fmtDay(f.start)} – ${fmtDay(f.end)}`}
                </p>
              </div>
              <input type="date" key={f.date} defaultValue={f.date} onBlur={(e) => edit(f, e.target.value)}
                className="rounded-lg border border-stone-300 bg-paper px-2 py-1 text-sm" aria-label={`${f.name} date`} />
              {f.user_edited && (
                <button onClick={() => api.resetFestival(f.id).then(load)} className="text-xs text-amber-700 underline" title="Restore the built-in date">
                  edited · reset
                </button>
              )}
              <button onClick={() => toggleHistory(f.festival)} className="rounded-lg px-3 py-1 text-sm text-stone-600 hover:bg-stone-100">
                {openKey === f.festival ? 'Hide' : 'Every year →'}
              </button>
            </div>
            {f.events.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {f.events.map((e) => (
                  <a key={e.id} href={`#/events/${e.id}`} className="flex items-center gap-2 rounded-full bg-amber-50 py-1 pl-1 pr-3 text-sm text-amber-900 hover:bg-amber-100">
                    {e.hero_media_id && <img src={thumbUrl(e.hero_media_id)} alt="" className="h-7 w-7 rounded-full object-cover" />}
                    {e.title} · {e.photo_count} photos
                  </a>
                ))}
              </div>
            )}
            {openKey === f.festival && <YearStrip years={history[f.festival] ?? null} empty={`No ${f.name} photos found in any year yet.`} />}
          </li>
        ))}
      </ul>
    </section>
  )
}
