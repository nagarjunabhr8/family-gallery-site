import { AnimatePresence, motion } from 'framer-motion'
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { api, thumbUrl } from '../api'
import type { EventSummary } from '../api'

export default function Events() {
  const [events, setEvents] = useState<EventSummary[] | null>(null)
  const [showMoments, setShowMoments] = useState(true)
  const [merging, setMerging] = useState<Set<number> | null>(null)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .events({ include_moments: showMoments })
      .then((d) => setEvents(d.events))
      .catch((e) => setError(e.message))
  }, [showMoments])

  useEffect(() => {
    load()
  }, [load])

  const byYear = useMemo(() => {
    const out: { year: number; events: EventSummary[] }[] = []
    for (const e of events ?? []) {
      const y = new Date(e.start_at).getFullYear()
      if (!out.length || out[out.length - 1].year !== y) out.push({ year: y, events: [] })
      out[out.length - 1].events.push(e)
    }
    return out
  }, [events])

  async function doMerge() {
    if (!merging || merging.size < 2) return
    try {
      const merged = await api.mergeEvents([...merging])
      setMerging(null)
      window.location.hash = `#/events/${merged.id}`
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const toggle = (id: number) =>
    setMerging((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  if (events && events.length === 0) {
    return (
      <div className="max-w-xl mx-auto text-center py-24">
        <h1 className="font-serif text-4xl text-stone-900">No events yet</h1>
        <p className="mt-4 text-stone-600">Events appear after your folders are scanned and analysed.</p>
        <a href="#/settings" className="mt-8 inline-block rounded-xl bg-stone-800 px-6 py-3 text-stone-50 hover:bg-stone-700">
          Go to Settings
        </a>
      </div>
    )
  }

  return (
    <div className="pb-24">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl text-stone-900">Events</h1>
          <p className="mt-1 text-sm text-stone-500">
            Photos grouped by when (and where) they were taken. Festivals and family days are recognised automatically.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 rounded-full bg-stone-200/70 px-3 py-1 text-sm text-stone-600 cursor-pointer">
            <input
              type="checkbox"
              checked={showMoments}
              onChange={(e) => setShowMoments(e.target.checked)}
              className="accent-amber-600"
            />
            Monthly moments
          </label>
          <button
            onClick={() => setMerging(merging ? null : new Set())}
            className={`rounded-full px-3 py-1 text-sm ${merging ? 'bg-amber-600 text-white' : 'bg-stone-200/70 text-stone-600 hover:bg-stone-200'}`}
          >
            {merging ? 'Cancel merge' : 'Merge events…'}
          </button>
          <button
            onClick={() => setCreating(true)}
            className="rounded-full bg-stone-800 px-4 py-1 text-sm text-stone-50 hover:bg-stone-700"
          >
            + New event
          </button>
        </div>
      </div>

      {error && <p className="mt-4 rounded-xl bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-800">{error}</p>}
      {merging && (
        <p className="mt-4 text-sm text-amber-800">Select the events that belong together, then press Merge.</p>
      )}

      <div className="mt-8 space-y-12">
        {byYear.map(({ year, events }) => (
          <section key={year}>
            <h2 className="font-serif text-3xl text-stone-800">{year}</h2>
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {events.map((e) => (
                <EventCard
                  key={e.id}
                  event={e}
                  selecting={!!merging}
                  selected={merging?.has(e.id) ?? false}
                  onSelect={() => toggle(e.id)}
                />
              ))}
            </div>
          </section>
        ))}
      </div>

      <AnimatePresence>
        {merging && merging.size > 0 && (
          <motion.div
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            className="fixed bottom-4 inset-x-4 z-30 mx-auto max-w-md rounded-2xl bg-stone-900 text-stone-100 shadow-2xl p-3 flex items-center gap-3"
          >
            <span className="px-2 text-sm">{merging.size} selected</span>
            <button
              disabled={merging.size < 2}
              onClick={doMerge}
              className="ml-auto rounded-lg bg-amber-600 px-4 py-1.5 text-sm hover:bg-amber-500 disabled:opacity-40"
            >
              Merge into one event
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {creating && <NewEventDialog onClose={() => setCreating(false)} />}
    </div>
  )
}

export function EventCard({
  event: e,
  selecting = false,
  selected = false,
  onSelect,
}: {
  event: EventSummary
  selecting?: boolean
  selected?: boolean
  onSelect?: () => void
}) {
  const body = (
    <>
      <div className="relative aspect-[4/3] overflow-hidden rounded-2xl bg-stone-200 shadow-sm">
        {e.hero_media_id && (
          <img
            src={thumbUrl(e.hero_media_id)}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
          />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/0 to-black/0" />
        <div className="absolute bottom-0 inset-x-0 p-4 text-white">
          <h3 className="font-serif text-xl leading-tight drop-shadow">{e.title}</h3>
          <p className="mt-0.5 text-xs text-white/80">
            {e.date_text} · {e.photo_count} photo{e.photo_count === 1 ? '' : 's'}
            {e.video_count > 0 && ` · ${e.video_count} video${e.video_count === 1 ? '' : 's'}`}
          </p>
        </div>
        {selecting && (
          <span
            className={`absolute top-3 right-3 h-7 w-7 rounded-full border-2 ${
              selected ? 'bg-amber-500 border-amber-500' : 'bg-black/20 border-white'
            }`}
          />
        )}
        {e.kind === 'moments' && (
          <span className="absolute top-3 left-3 rounded-full bg-white/85 px-2 py-0.5 text-[11px] text-stone-700">
            Moments
          </span>
        )}
      </div>
      {(e.occasions.length > 0 || e.tags.length > 0) && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {e.occasions.map((o) => (
            <span key={o.key + o.date} className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
              {o.name}
            </span>
          ))}
          {e.tags.map((t) => (
            <span key={t.tag} className="rounded-full bg-stone-200 px-2 py-0.5 text-xs text-stone-700">
              {t.label}
            </span>
          ))}
        </div>
      )}
    </>
  )
  if (selecting) {
    return (
      <button onClick={onSelect} className={`group text-left rounded-2xl ${selected ? 'ring-4 ring-amber-500 ring-offset-4 ring-offset-stone-50' : ''}`}>
        {body}
      </button>
    )
  }
  return (
    <a href={`#/events/${e.id}`} className="group block">
      {body}
    </a>
  )
}

function NewEventDialog({ onClose }: { onClose: () => void }) {
  const [title, setTitle] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(ev: FormEvent) {
    ev.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const e = await api.createEvent({ title, start, end: end || start })
      window.location.hash = `#/events/${e.id}`
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <form
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-2xl bg-stone-50 p-6 shadow-2xl space-y-4"
      >
        <h2 className="font-serif text-2xl text-stone-900">New event</h2>
        <p className="text-sm text-stone-600">
          All photos taken in these dates join this event (except ones you've placed by hand).
        </p>
        <input
          autoFocus
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Tirupati trip"
          className="w-full rounded-xl border border-stone-300 bg-white px-4 py-2.5 outline-none focus:border-stone-500"
        />
        <div className="grid grid-cols-2 gap-3 text-sm">
          <label className="text-stone-600">
            From
            <input type="date" required value={start} onChange={(e) => setStart(e.target.value)}
              className="mt-1 w-full rounded-lg border border-stone-300 bg-white px-2 py-1.5" />
          </label>
          <label className="text-stone-600">
            To
            <input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)}
              className="mt-1 w-full rounded-lg border border-stone-300 bg-white px-2 py-1.5" />
          </label>
        </div>
        {error && <p className="text-sm text-rose-700">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-xl px-4 py-2 text-sm text-stone-600 hover:bg-stone-200">
            Cancel
          </button>
          <button disabled={busy} className="rounded-xl bg-stone-800 px-5 py-2 text-sm text-stone-50 hover:bg-stone-700 disabled:opacity-40">
            Create
          </button>
        </div>
      </form>
    </div>
  )
}
