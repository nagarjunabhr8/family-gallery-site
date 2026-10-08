import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { story } from '../api'
import type { MediaItem } from '../api'
import Thumb, { rotationStyle } from '../components/Photo'
import Slideshow from '../components/Slideshow'
import Viewer from '../components/Viewer'
import { thumbUrl } from '../api'

type YearInfo = { year: number; photo_count: number; cover_media_id: number | null }

export default function BestOfYear({ year }: { year: number | null }) {
  const [years, setYears] = useState<YearInfo[] | null>(null)
  const [items, setItems] = useState<MediaItem[] | null>(null)
  const [total, setTotal] = useState(0)
  const [viewer, setViewer] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    story.bestYears().then(setYears)
  }, [])

  const current = year ?? years?.[0]?.year ?? null

  useEffect(() => {
    if (current === null) return
    setItems(null)
    story.bestOf(current, 24).then((d) => {
      setItems(d.items)
      setTotal(d.photo_count)
    })
  }, [current])

  if (years && years.length === 0) {
    return <p className="py-24 text-center text-stone-500">No photos yet.</p>
  }

  return (
    <div className="pb-24">
      <a href="#/" className="text-sm text-stone-500 hover:text-stone-800">
        ← Our Story
      </a>
      <header className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-stone-500">Best of</p>
          <h1 className="font-serif text-6xl text-stone-900">{current ?? ''}</h1>
          {items && (
            <p className="mt-2 text-sm text-stone-500">
              {items.length} favourites out of {total} photos, picked for quality, faces and variety
            </p>
          )}
        </div>
        {items && items.length > 0 && (
          <button onClick={() => setPlaying(true)} className="rounded-full bg-stone-900 px-6 py-3 text-stone-50 shadow-lg hover:bg-stone-800">
            ▶  Play {current}
          </button>
        )}
      </header>

      {/* year strip */}
      <div className="mt-8 flex gap-3 overflow-x-auto pb-3">
        {years?.map((y) => (
          <a key={y.year} href={`#/best/${y.year}`} className="group shrink-0 w-24 text-center">
            <div className={`aspect-square overflow-hidden rounded-2xl bg-stone-200 ring-offset-2 ring-offset-stone-50 ${y.year === current ? 'ring-2 ring-amber-600' : ''}`}>
              {y.cover_media_id && <Thumb id={y.cover_media_id} className="transition group-hover:scale-105" />}
            </div>
            <p className={`mt-1 font-serif text-lg ${y.year === current ? 'text-stone-900' : 'text-stone-500'}`}>{y.year}</p>
          </a>
        ))}
      </div>

      <div className="mt-8 columns-2 sm:columns-3 lg:columns-4 gap-4 [&>*]:mb-4">
        {items?.map((m, i) => (
          <motion.button
            key={m.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.04, 0.6), duration: 0.5 }}
            onClick={() => setViewer(i)}
            className="group block w-full overflow-hidden rounded-2xl bg-stone-200 break-inside-avoid shadow-sm"
          >
            <img
              src={thumbUrl(m.id)}
              alt={m.filename}
              loading="lazy"
              style={{
                aspectRatio: m.width && m.height ? (m.rotation === 90 || m.rotation === 270 ? `${m.height} / ${m.width}` : `${m.width} / ${m.height}`) : undefined,
                ...rotationStyle(m.rotation, false),
              }}
              className="w-full object-cover transition duration-500 group-hover:scale-[1.03]"
            />
          </motion.button>
        ))}
      </div>

      {viewer !== null && items && (
        <Viewer items={items} index={viewer} onIndex={setViewer} onClose={() => setViewer(null)} />
      )}
      {playing && items && <Slideshow items={items} title={`Best of ${current}`} onClose={() => setPlaying(false)} />}
    </div>
  )
}
