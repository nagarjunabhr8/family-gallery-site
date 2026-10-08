import { motion } from 'framer-motion'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, DATE_SOURCE_LABEL, formatDate, formatDuration, thumbUrl } from '../api'
import type { DateSource, Kind, MediaItem, Stats } from '../api'
import Viewer from '../components/Viewer'

const PAGE = 200

interface Filters {
  kind?: Kind
  date_source?: DateSource
  include_duplicates?: boolean
}

export default function Library() {
  const [items, setItems] = useState<MediaItem[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<Stats | null>(null)
  const [filters, setFilters] = useState<Filters>({})
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState<number | null>(null)
  const sentinel = useRef<HTMLDivElement>(null)
  const loadingRef = useRef(false)

  useEffect(() => {
    api.stats().then(setStats).catch(() => {})
  }, [])

  // Reset when filters change
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .media({ ...filters, offset: 0, limit: PAGE })
      .then((page) => {
        if (cancelled) return
        setItems(page.items)
        setTotal(page.total)
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [filters])

  const loadMore = useCallback(async () => {
    if (loadingRef.current || items.length >= total) return
    loadingRef.current = true
    try {
      const page = await api.media({ ...filters, offset: items.length, limit: PAGE })
      setItems((prev) => [...prev, ...page.items])
      setTotal(page.total)
    } finally {
      loadingRef.current = false
    }
  }, [filters, items.length, total])

  useEffect(() => {
    const el = sentinel.current
    if (!el) return
    const obs = new IntersectionObserver((entries) => entries[0].isIntersecting && loadMore(), {
      rootMargin: '800px',
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [loadMore])

  const groups = useMemo(() => groupByMonth(items), [items])
  const indexOf = useMemo(() => new Map(items.map((m, i) => [m.id, i])), [items])

  if (stats && stats.total === 0) {
    return (
      <div className="max-w-xl mx-auto text-center py-24">
        <h1 className="font-serif text-4xl text-stone-900">Your memories will live here</h1>
        <p className="mt-4 text-stone-600">Add a photo folder and run a scan to fill your library.</p>
        <a
          href="#/settings"
          className="mt-8 inline-block rounded-xl bg-stone-800 px-6 py-3 text-stone-50 hover:bg-stone-700"
        >
          Add a folder
        </a>
      </div>
    )
  }

  return (
    <div>
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl text-stone-900">Library</h1>
          {stats && (
            <p className="mt-1 text-sm text-stone-500">
              {stats.photos.toLocaleString()} photos · {stats.videos.toLocaleString()} videos
              {stats.by_year.length > 0 &&
                ` · ${stats.by_year[0].year}–${stats.by_year[stats.by_year.length - 1].year}`}
              {stats.with_errors > 0 && ` · ${stats.with_errors} with problems`}
              {stats.hidden_duplicates > 0 && (
                <>
                  {' · '}
                  <a href="#/duplicates" className="underline hover:text-stone-800">
                    {stats.hidden_duplicates} similar cop{stats.hidden_duplicates === 1 ? 'y' : 'ies'} tucked away
                  </a>
                </>
              )}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Chips
            value={filters.kind}
            options={[
              [undefined, 'All'],
              ['photo', 'Photos'],
              ['video', 'Videos'],
            ]}
            onChange={(kind) => setFilters((f) => ({ ...f, kind }))}
          />
          <Chips
            value={filters.date_source}
            options={[
              [undefined, 'Any date'],
              ['exif', 'Camera'],
              ['filename', 'Filename'],
              ['mtime', 'File date'],
            ]}
            onChange={(date_source) => setFilters((f) => ({ ...f, date_source }))}
          />
          <label className="flex items-center gap-2 rounded-full bg-stone-200/70 px-3 py-1 text-sm text-stone-600 cursor-pointer">
            <input
              type="checkbox"
              checked={!!filters.include_duplicates}
              onChange={(e) => setFilters((f) => ({ ...f, include_duplicates: e.target.checked || undefined }))}
              className="accent-amber-600"
            />
            Show all copies
          </label>
        </div>
      </div>

      {stats && Object.keys(stats.by_date_source).length > 0 && (
        <p className="mt-3 text-xs text-stone-500">
          Dates from:{' '}
          {(Object.entries(stats.by_date_source) as [DateSource, number][])
            .map(([src, n]) => `${DATE_SOURCE_LABEL[src]} ${n.toLocaleString()}`)
            .join(' · ')}
        </p>
      )}

      {!loading && items.length === 0 && (
        <p className="mt-16 text-center text-stone-500">Nothing matches these filters.</p>
      )}

      <div className="mt-6 space-y-10">
        {groups.map((g) => (
          <section key={g.key}>
            <h2 className="sticky top-16 z-10 -mx-4 sm:-mx-6 px-4 sm:px-6 py-2 bg-stone-50/90 backdrop-blur font-serif text-xl text-stone-800">
              {g.label} <span className="text-sm font-sans text-stone-400">{g.items.length}</span>
            </h2>
            <div className="mt-2 grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 xl:grid-cols-8 gap-1.5">
              {g.items.map((m) => (
                <Tile key={m.id} item={m} onOpen={() => setOpen(indexOf.get(m.id) ?? null)} />
              ))}
            </div>
          </section>
        ))}
      </div>

      <div ref={sentinel} className="h-10" />
      {items.length > 0 && items.length < total && (
        <p className="text-center text-sm text-stone-400 py-6">Loading more…</p>
      )}

      {open !== null && (
        <Viewer
          items={items}
          index={open}
          onIndex={(i) => {
            setOpen(i)
            if (i >= items.length - 5) loadMore()
          }}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  )
}

function Tile({ item, onOpen }: { item: MediaItem; onOpen: () => void }) {
  return (
    <motion.button
      onClick={onOpen}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      whileHover={{ scale: 1.02 }}
      className="group relative aspect-square overflow-hidden rounded-lg bg-stone-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-600"
      title={`${item.filename}\n${formatDate(item.taken_at, true)} · ${DATE_SOURCE_LABEL[item.date_source]}`}
    >
      {item.has_thumb ? (
        <img src={thumbUrl(item.id)} alt={item.filename} loading="lazy" className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full w-full items-center justify-center p-2 text-xs text-stone-500 break-all">
          {item.kind === 'video' ? '▶ ' : ''}
          {item.filename}
        </div>
      )}
      {item.kind === 'video' && (
        <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
          ▶ {formatDuration(item.duration_s)}
        </span>
      )}
      {item.date_confidence === 'low' && (
        <span
          className="absolute top-1.5 left-1.5 h-2 w-2 rounded-full bg-amber-500 ring-2 ring-white/80"
          aria-label="Date guessed from file modified time"
        />
      )}
      {(item.group_size ?? 1) > 1 && (
        <span
          className="absolute bottom-1 left-1 rounded bg-amber-600/90 px-1.5 py-0.5 text-[10px] font-medium text-white"
          title={`Best of ${item.group_size} similar photos`}
        >
          +{(item.group_size ?? 1) - 1}
        </span>
      )}
      {item.error && (
        <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-rose-500 ring-2 ring-white/80" />
      )}
    </motion.button>
  )
}

function Chips<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T | undefined
  options: [T | undefined, string][]
  onChange: (v: T | undefined) => void
}) {
  return (
    <div className="flex rounded-full bg-stone-200/70 p-0.5">
      {options.map(([v, label]) => (
        <button
          key={label}
          onClick={() => onChange(v)}
          className={`rounded-full px-3 py-1 text-sm transition-colors ${
            value === v ? 'bg-white text-stone-900 shadow-sm' : 'text-stone-600 hover:text-stone-900'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

function groupByMonth(items: MediaItem[]) {
  const groups: { key: string; label: string; items: MediaItem[] }[] = []
  for (const m of items) {
    const d = new Date(m.taken_at)
    const key = `${d.getFullYear()}-${d.getMonth()}`
    let g = groups[groups.length - 1]
    if (!g || g.key !== key) {
      g = { key, label: d.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' }), items: [] }
      groups.push(g)
    }
    g.items.push(m)
  }
  return groups
}
