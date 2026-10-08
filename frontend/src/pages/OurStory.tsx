import { motion } from 'framer-motion'
import { useCallback, useEffect, useState } from 'react'
import { api, personLabel, story } from '../api'
import type { MediaItem, Person, Story, StoryChapter, StoryStage } from '../api'
import OnThisDay from '../components/OnThisDay'
import Thumb from '../components/Photo'
import Slideshow from '../components/Slideshow'
import Viewer from '../components/Viewer'
import { EventCard } from './Events'

function yearOf(iso: string | null): number | null {
  return iso ? new Date(iso).getFullYear() : null
}

function fmtDate(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

export default function OurStory() {
  const [data, setData] = useState<Story | null>(null)
  const [people, setPeople] = useState<Person[]>([])
  const [editing, setEditing] = useState(false)
  const [viewer, setViewer] = useState<{ items: MediaItem[]; index: number } | null>(null)
  const [show, setShow] = useState<{ items: MediaItem[]; title: string } | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    story.get().then(setData).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    load()
    api.people().then((d) => setPeople(d.people.filter((p) => p.name)))
  }, [load])

  async function playStory() {
    setPreparing(true)
    try {
      const years = (await story.bestYears()).sort((a, b) => a.year - b.year)
      const per = years.length > 15 ? 5 : years.length > 6 ? 8 : 12
      const sets = await Promise.all(years.map((y) => story.bestOf(y.year, per)))
      setShow({ items: sets.flatMap((s) => s.items), title: data?.owner?.name ? `${data.owner.name}'s story` : 'Our story' })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setPreparing(false)
    }
  }

  if (error && !data) return <p className="text-rose-700">{error}</p>
  if (!data) return null

  if (data.photo_count === 0) {
    return (
      <div className="max-w-xl mx-auto text-center py-24">
        <h1 className="font-serif text-5xl text-stone-900">Our Story</h1>
        <p className="mt-4 text-stone-600">Add a photo folder and run a scan, and your family's story will appear here.</p>
        <a href="#/settings" className="mt-8 inline-block rounded-xl bg-stone-800 px-6 py-3 text-stone-50 hover:bg-stone-700">
          Add a folder
        </a>
      </div>
    )
  }

  const first = yearOf(data.first)
  const last = yearOf(data.last)
  const allYears = data.chapters.flatMap((c) => c.years.map((y) => y.year))

  return (
    <div className="pb-24">
      {/* title */}
      <header className="py-6 sm:py-12 text-center animate-fade-in">
        <p className="text-xs uppercase tracking-[0.3em] text-stone-500">
          {first === last ? first : `${first} — ${last}`}
        </p>
        <h1 className="mt-3 font-serif text-5xl sm:text-7xl text-stone-900">
          {data.owner?.name ? `${data.owner.name}'s Story` : 'Our Story'}
        </h1>
        <p className="mt-4 text-stone-600">
          {data.photo_count.toLocaleString()} photos · {data.event_count} moments worth remembering
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <button
            onClick={playStory}
            disabled={preparing}
            className="rounded-full bg-stone-900 px-6 py-3 text-stone-50 shadow-lg hover:bg-stone-800 disabled:opacity-60"
          >
            {preparing ? 'Preparing…' : '▶  Play our story'}
          </button>
          <a href="#/best" className="rounded-full bg-paper px-6 py-3 text-stone-800 ring-1 ring-stone-300 hover:bg-stone-100">
            Best of each year
          </a>
          <button onClick={() => setEditing(true)} className="rounded-full px-6 py-3 text-stone-600 hover:bg-stone-200/60">
            {data.stages.length ? 'Edit chapters' : 'Add life chapters'}
          </button>
        </div>
      </header>

      <OnThisDay onOpen={(items, index) => setViewer({ items, index })} />

      {data.stages.length === 0 && (
        <ChapterInvite people={people} owner={data.owner?.id ?? null} onDone={load} />
      )}

      <div className="mt-12 lg:grid lg:grid-cols-[1fr_5rem] lg:gap-10">
        <div className="space-y-20">
          {data.chapters.map((ch) => (
            <ChapterBlock key={`${ch.stage_id}-${ch.name}`} chapter={ch} />
          ))}
        </div>
        <nav className="hidden lg:block">
          <ol className="sticky top-24 space-y-1 text-right text-sm">
            {allYears.map((y) => (
              <li key={y}>
                <a href={`#/`} onClick={(e) => {
                  e.preventDefault()
                  document.getElementById(`year-${y}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                }} className="text-stone-400 hover:text-stone-900 tabular-nums">
                  {y}
                </a>
              </li>
            ))}
          </ol>
        </nav>
      </div>

      {editing && (
        <StageEditor
          stages={data.stages}
          people={people}
          owner={data.owner?.id ?? null}
          onClose={() => setEditing(false)}
          onChanged={load}
        />
      )}
      {viewer && (
        <Viewer items={viewer.items} index={viewer.index} onIndex={(i) => setViewer({ ...viewer, index: i })} onClose={() => setViewer(null)} />
      )}
      {show && <Slideshow items={show.items} title={show.title} onClose={() => setShow(null)} />}
    </div>
  )
}

function ChapterBlock({ chapter: ch }: { chapter: StoryChapter }) {
  return (
    <section>
      {ch.name && (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.7 }}
          className="mb-10 text-center"
        >
          <div className="mx-auto mb-4 h-px w-16 bg-amber-600/60" />
          <h2 className="font-serif text-4xl sm:text-5xl text-stone-900">{ch.name}</h2>
          <p className="mt-2 text-sm text-stone-500">
            {[ch.age, ch.start && `from ${fmtDate(ch.start)}`].filter(Boolean).join(' · ')}
          </p>
        </motion.div>
      )}
      <div className="space-y-14">
        {ch.years.map((y) => {
          const big = y.events.filter((e) => e.kind !== 'moments')
          const moments = y.events.filter((e) => e.kind === 'moments')
          return (
            <motion.div
              key={y.year}
              id={`year-${y.year}`}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.6 }}
              className="scroll-mt-24 md:grid md:grid-cols-[9rem_1fr] md:gap-8"
            >
              <div className="md:sticky md:top-24 self-start">
                <a href={`#/best/${y.year}`} className="group block">
                  <p className="font-serif text-5xl text-stone-900 group-hover:text-amber-700 transition-colors">{y.year}</p>
                </a>
                {y.age && <p className="mt-1 text-sm text-stone-500">{y.age}</p>}
                {y.photo_count > 0 && (
                  <a href={`#/best/${y.year}`} className="mt-1 inline-block text-xs text-stone-500 underline-offset-2 hover:underline">
                    Best of {y.year} →
                  </a>
                )}
              </div>
              <div className="mt-4 md:mt-0 space-y-5">
                {y.milestones.map((m) => (
                  <p key={m.label + m.date} className="flex items-center gap-3 font-serif text-lg italic text-amber-800">
                    <span className="text-amber-600">✦</span> {m.label}
                    <span className="font-sans text-xs not-italic text-stone-500">{fmtDate(m.date)}</span>
                  </p>
                ))}
                {big.length > 0 && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5">
                    {big.map((e) => (
                      <EventCard key={e.id} event={e} />
                    ))}
                  </div>
                )}
                {moments.length > 0 && (
                  <div className="flex gap-3 overflow-x-auto pb-2">
                    {moments.map((e) => (
                      <a key={e.id} href={`#/events/${e.id}`} className="group w-40 shrink-0">
                        <div className="aspect-square overflow-hidden rounded-xl bg-stone-200">
                          {e.hero_media_id && <Thumb id={e.hero_media_id} className="transition group-hover:scale-105" />}
                        </div>
                        <p className="mt-1 truncate text-sm text-stone-700">{e.title.replace('Moments · ', '')}</p>
                        <p className="text-xs text-stone-500">{e.photo_count} photo{e.photo_count === 1 ? '' : 's'}</p>
                      </a>
                    ))}
                  </div>
                )}
                {big.length === 0 && moments.length === 0 && y.milestones.length === 0 && (
                  <p className="text-sm text-stone-400">No photos from this year yet.</p>
                )}
              </div>
            </motion.div>
          )
        })}
      </div>

    </section>
  )
}

function ChapterInvite({ people, owner, onDone }: { people: Person[]; owner: number | null; onDone: () => void }) {
  const [pid, setPid] = useState<number | ''>(owner ?? people.find((p) => p.birth_date)?.id ?? '')
  const [error, setError] = useState<string | null>(null)
  const chosen = people.find((p) => p.id === pid)

  async function go() {
    setError(null)
    try {
      await story.suggest(pid === '' ? null : pid)
      onDone()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <section className="mt-12 rounded-3xl bg-paper p-6 sm:p-8 ring-1 ring-stone-200 text-center">
      <h2 className="font-serif text-2xl text-stone-900">Tell it in chapters</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm text-stone-600">
        Choose whose story this is. From their birth date, your wedding anniversary and the children's birth dates, the
        app suggests chapters like Childhood, School days, College, Marriage and Our little ones. You can rename or change
        any of them.
      </p>
      {people.length === 0 ? (
        <p className="mt-4 text-sm text-stone-500">
          First name the people in your photos on the <a href="#/people" className="underline">People</a> page.
        </p>
      ) : (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
          <select
            value={pid}
            onChange={(e) => setPid(e.target.value ? Number(e.target.value) : '')}
            className="rounded-xl border border-stone-300 bg-paper px-3 py-2"
          >
            <option value="">Whose story?</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {personLabel(p)}
                {p.birth_date ? '' : ' (no birth date yet)'}
              </option>
            ))}
          </select>
          <button
            onClick={go}
            disabled={!chosen}
            className="rounded-xl bg-stone-800 px-5 py-2 text-stone-50 hover:bg-stone-700 disabled:opacity-40"
          >
            Suggest chapters
          </button>
        </div>
      )}
      {chosen && !chosen.birth_date && (
        <p className="mt-3 text-sm text-amber-800">
          Add {chosen.name}'s birth date on <a className="underline" href={`#/people/${chosen.id}`}>their page</a> first.
        </p>
      )}
      {error && <p className="mt-3 text-sm text-rose-700">{error}</p>}
    </section>
  )
}

function StageEditor({
  stages,
  people,
  owner,
  onClose,
  onChanged,
}: {
  stages: StoryStage[]
  people: Person[]
  owner: number | null
  onClose: () => void
  onChanged: () => void
}) {
  const [newName, setNewName] = useState('')
  const [newStart, setNewStart] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function act(fn: () => Promise<unknown>) {
    setError(null)
    try {
      await fn()
      onChanged()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-stone-50 p-6 shadow-2xl">
        <h2 className="font-serif text-2xl text-stone-900">Life chapters</h2>
        <p className="mt-1 text-sm text-stone-600">Each chapter runs until the next one starts.</p>

        <label className="mt-4 flex items-center gap-2 text-sm text-stone-600">
          Whose story
          <select
            defaultValue={owner ?? ''}
            onChange={(e) => act(() => story.setOwner(e.target.value ? Number(e.target.value) : null))}
            className="rounded-lg border border-stone-300 bg-paper px-2 py-1"
          >
            <option value="">Nobody in particular</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>{personLabel(p)}</option>
            ))}
          </select>
        </label>

        <ul className="mt-5 space-y-2">
          {stages.map((st) => (
            <li key={st.id} className="flex items-center gap-2">
              <input
                defaultValue={st.name}
                onBlur={(e) => e.target.value.trim() && e.target.value !== st.name && act(() => story.editStage(st.id, e.target.value, st.start))}
                className="flex-1 min-w-0 rounded-lg border border-stone-300 bg-paper px-3 py-1.5"
              />
              <input
                type="date"
                defaultValue={st.start}
                onBlur={(e) => e.target.value && e.target.value !== st.start && act(() => story.editStage(st.id, st.name, e.target.value))}
                className="rounded-lg border border-stone-300 bg-paper px-2 py-1.5 text-sm"
              />
              <button onClick={() => act(() => story.deleteStage(st.id))} className="px-2 text-rose-700" aria-label={`Remove ${st.name}`}>
                ✕
              </button>
            </li>
          ))}
        </ul>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            act(async () => {
              await story.addStage(newName, newStart)
              setNewName('')
              setNewStart('')
            })
          }}
          className="mt-4 flex items-center gap-2"
        >
          <input value={newName} onChange={(e) => setNewName(e.target.value)} required placeholder="New chapter, e.g. Bengaluru years"
            className="flex-1 min-w-0 rounded-lg border border-dashed border-stone-400 bg-transparent px-3 py-1.5" />
          <input type="date" value={newStart} onChange={(e) => setNewStart(e.target.value)} required
            className="rounded-lg border border-dashed border-stone-400 bg-transparent px-2 py-1.5 text-sm" />
          <button className="rounded-lg bg-stone-800 px-3 py-1.5 text-sm text-stone-50">Add</button>
        </form>

        {error && <p className="mt-3 text-sm text-rose-700">{error}</p>}
        <div className="mt-6 flex justify-between">
          <button
            onClick={() => act(() => story.suggest(owner))}
            className="rounded-lg px-3 py-1.5 text-sm text-stone-600 hover:bg-stone-200"
            title="Re-create the suggested chapters (your edited ones stay)"
          >
            Suggest again
          </button>
          <button onClick={onClose} className="rounded-xl bg-stone-800 px-5 py-2 text-sm text-stone-50 hover:bg-stone-700">
            Done
          </button>
        </div>
      </div>
    </div>
  )
}
