import { AnimatePresence, motion } from 'framer-motion'
import { useCallback, useEffect, useState } from 'react'
import { api, formatDate, formatDuration, originalUrl, thumbUrl } from '../api'
import type { EventDetail, EventSummary, MediaItem } from '../api'
import Viewer from '../components/Viewer'

export default function EventPage({ id }: { id: number }) {
  const [event, setEvent] = useState<EventDetail | null>(null)
  const [others, setOthers] = useState<EventSummary[]>([])
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [selecting, setSelecting] = useState(false)
  const [viewer, setViewer] = useState<{ items: MediaItem[]; index: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.event(id).then(setEvent).catch((e) => setError(e.message))
  }, [id])

  useEffect(() => {
    load()
    api.events({ include_moments: true }).then((d) => setOthers(d.events.filter((e) => e.id !== id)))
  }, [id, load])

  if (error && !event) return <p className="text-rose-700">{error}</p>
  if (!event) return null

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      setSelected(new Set())
      setSelecting(false)
      load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const toggle = (mid: number) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(mid)) next.delete(mid)
      else next.add(mid)
      return next
    })

  const one = selected.size === 1 ? [...selected][0] : null
  const visible = event.media.filter((m) => !m.hidden_copy)

  return (
    <div className="pb-28">
      <a href="#/events" className="text-sm text-stone-500 hover:text-stone-800">
        ← Events
      </a>

      {/* hero */}
      <header className="relative mt-4 overflow-hidden rounded-3xl bg-stone-900 shadow-lg">
        {event.hero_media_id && (
          <motion.img
            key={event.hero_media_id}
            initial={{ opacity: 0, scale: 1.03 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6 }}
            src={originalUrl(event.hero_media_id)}
            alt=""
            className="h-[52vh] min-h-72 w-full object-cover opacity-90"
          />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/10 to-transparent" />
        <div className="absolute bottom-0 inset-x-0 p-6 sm:p-10 text-white">
          <textarea
            key={`t-${event.title}`}
            defaultValue={event.title}
            aria-label="Event title"
            rows={1}
            onBlur={(e) => {
              const v = e.target.value.replace(/\s+/g, ' ').trim()
              if (v !== event.title) run(() => api.updateEvent(event.id, { title: v || null }))
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                ;(e.target as HTMLTextAreaElement).blur()
              }
            }}
            className="field-sizing-content w-full resize-none bg-transparent font-serif text-3xl leading-tight sm:text-5xl outline-none drop-shadow placeholder:text-white/50 focus:border-b focus:border-white/40"
          />
          <p className="mt-2 text-sm text-white/85">
            {event.date_text}
            {event.days > 1 && ` · ${event.days} days`} · {event.photo_count} photo{event.photo_count === 1 ? '' : 's'}
            {event.video_count > 0 && ` · ${event.video_count} video${event.video_count === 1 ? '' : 's'}`}
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {event.occasions.map((o) => (
              <span key={o.key + o.date} className="rounded-full bg-amber-400/90 px-2.5 py-0.5 text-xs text-stone-900">
                {o.name}
              </span>
            ))}
            {event.tags.map((t) => (
              <span key={t.tag} className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs backdrop-blur">
                {t.label}
              </span>
            ))}
            {event.people.filter((p) => p.name).map((p) => (
              <a key={p.id} href={`#/people/${p.id}`} className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs backdrop-blur hover:bg-white/30">
                {p.name}
              </a>
            ))}
          </div>
        </div>
      </header>

      <textarea
        key={`d-${event.description}`}
        defaultValue={event.description ?? ''}
        placeholder="Add a note about this day…"
        rows={2}
        onBlur={(e) => {
          const v = e.target.value.trim()
          if (v !== (event.description ?? '')) run(() => api.updateEvent(event.id, { description: v || null }))
        }}
        className="mt-6 w-full resize-none bg-transparent font-serif text-lg italic text-stone-700 outline-none placeholder:text-stone-400"
      />

      {error && <p className="mt-2 rounded-xl bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-800">{error}</p>}

      {/* highlights */}
      {event.curated.length > 0 && (
        <section className="mt-6">
          <h2 className="font-serif text-2xl text-stone-900">Highlights</h2>
          <p className="text-sm text-stone-500">
            The best {event.curated.length === 1 ? 'shot' : `${event.curated.length} shots`}, without look-alikes.
          </p>
          <div className="mt-4 columns-2 sm:columns-3 lg:columns-4 gap-3 [&>*]:mb-3">
            {event.curated.map((m, i) => (
              <button
                key={m.id}
                onClick={() => setViewer({ items: event.curated, index: i })}
                className="group block w-full overflow-hidden rounded-2xl bg-stone-200 break-inside-avoid"
              >
                <img
                  src={thumbUrl(m.id)}
                  alt={m.filename}
                  loading="lazy"
                  style={{ aspectRatio: m.width && m.height ? `${m.width} / ${m.height}` : undefined }}
                  className="w-full object-cover transition duration-500 group-hover:scale-[1.03]"
                />
              </button>
            ))}
          </div>
        </section>
      )}

      {/* everything */}
      <section className="mt-10">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="font-serif text-2xl text-stone-900">All photos &amp; videos</h2>
            <p className="text-sm text-stone-500">
              {event.media.length} items
              {event.media.length !== visible.length && ` (${event.media.length - visible.length} similar copies dimmed)`}
            </p>
          </div>
          <button
            onClick={() => {
              setSelecting(!selecting)
              setSelected(new Set())
            }}
            className={`rounded-full px-4 py-1.5 text-sm ${selecting ? 'bg-amber-600 text-white' : 'bg-stone-200/70 text-stone-700 hover:bg-stone-200'}`}
          >
            {selecting ? 'Done' : 'Select / edit'}
          </button>
        </div>
        <div className="mt-4 grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
          {event.media.map((m, i) => {
            const on = selected.has(m.id)
            return (
              <button
                key={m.id}
                onClick={() => (selecting ? toggle(m.id) : setViewer({ items: event.media, index: i }))}
                className={`relative aspect-square overflow-hidden rounded-lg bg-stone-200 ${m.hidden_copy ? 'opacity-50' : ''} ${
                  on ? 'ring-4 ring-amber-500' : ''
                }`}
                title={`${m.filename}\n${formatDate(m.taken_at, true)}`}
              >
                {m.has_thumb && <img src={thumbUrl(m.id)} alt="" loading="lazy" className="h-full w-full object-cover" />}
                {m.kind === 'video' && (
                  <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1 text-[10px] text-white">
                    ▶ {formatDuration(m.duration_s)}
                  </span>
                )}
                {m.id === event.hero_media_id && (
                  <span className="absolute top-1 left-1 rounded bg-amber-500 px-1 text-[10px] text-white">cover</span>
                )}
              </button>
            )
          })}
        </div>
      </section>

      <section className="mt-12 flex flex-wrap gap-3 text-sm">
        {event.hero_by_user && (
          <button
            disabled={busy}
            onClick={() => run(() => api.updateEvent(event.id, { hero_media_id: null }))}
            className="rounded-lg border border-stone-300 px-3 py-1.5 hover:bg-stone-100"
          >
            Let the app choose the cover
          </button>
        )}
        {event.locked && (
          <button
            disabled={busy}
            onClick={async () => {
              if (!window.confirm('Undo your changes to this event? Its photos go back to automatic grouping (they are not deleted).')) return
              await api.dissolveEvent(event.id)
              window.location.hash = '#/events'
            }}
            className="rounded-lg px-3 py-1.5 text-rose-700 hover:bg-rose-50"
          >
            {event.kind === 'custom' ? 'Remove this event' : 'Undo my edits to this event'}
          </button>
        )}
      </section>

      <AnimatePresence>
        {selecting && selected.size > 0 && (
          <motion.div
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            className="fixed bottom-4 inset-x-4 z-30 mx-auto max-w-3xl rounded-2xl bg-stone-900 text-stone-100 shadow-2xl p-3 flex flex-wrap items-center gap-2"
          >
            <span className="px-2 text-sm">{selected.size} selected</span>
            {one !== null && (
              <>
                <button disabled={busy} onClick={() => run(() => api.updateEvent(event.id, { hero_media_id: one }))}
                  className="rounded-lg bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20">
                  Use as cover
                </button>
                <button
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      const r = await api.splitEvent(event.id, one)
                      window.location.hash = `#/events/${r.new_event_id}`
                    })
                  }
                  className="rounded-lg bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20"
                  title="This photo and everything after it become a new event"
                >
                  Split from here
                </button>
              </>
            )}
            <select
              disabled={busy}
              value=""
              onChange={(e) => e.target.value && run(() => api.moveMedia([...selected], Number(e.target.value)))}
              className="max-w-56 rounded-lg bg-white/10 px-3 py-1.5 text-sm text-stone-100 [&>option]:text-stone-900"
            >
              <option value="">Move to event…</option>
              {others.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.title} ({o.date_text})
                </option>
              ))}
            </select>
            <button
              disabled={busy}
              onClick={() => {
                const name = window.prompt('Name for the new event:')
                if (name !== null)
                  run(async () => {
                    const r = await api.moveMedia([...selected], null, name)
                    window.location.hash = `#/events/${r.event_id}`
                  })
              }}
              className="rounded-lg bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20"
            >
              New event…
            </button>
            <button onClick={() => setSelected(new Set())} className="ml-auto px-3 py-1.5 text-sm text-stone-400 hover:text-white">
              Clear
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {viewer && (
        <Viewer
          items={viewer.items}
          index={viewer.index}
          onIndex={(i) => setViewer({ ...viewer, index: i })}
          onClose={() => setViewer(null)}
        />
      )}
    </div>
  )
}
