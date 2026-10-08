import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'
import { api, DATE_SOURCE_LABEL, faceUrl, formatBytes, formatDate, originalUrl, story, TAG_LABEL } from '../api'
import type { MediaDetail, MediaItem } from '../api'
import QualityBars from './QualityBars'
import Slideshow from './Slideshow'

interface Props {
  items: MediaItem[]
  index: number
  onIndex: (i: number) => void
  onClose: () => void
}

export default function Viewer({ items, index, onIndex, onClose }: Props) {
  const item = items[index]
  const [detail, setDetail] = useState<MediaDetail | null>(null)
  const [showInfo, setShowInfo] = useState(() => window.innerWidth >= 1024)
  const [rotations, setRotations] = useState<Record<number, number>>({})
  const [zoom, setZoom] = useState<{ x: number; y: number } | null>(null)
  const [slideshow, setSlideshow] = useState(false)
  const touch = useRef<{ x: number; y: number; t: number } | null>(null)
  const lastTap = useRef(0)

  const rotation = rotations[item.id] ?? item.rotation ?? 0
  const sideways = rotation === 90 || rotation === 270

  useEffect(() => {
    let cancelled = false
    setDetail(null)
    setZoom(null)
    api.mediaDetail(item.id).then((d) => !cancelled && setDetail(d))
    return () => {
      cancelled = true
    }
  }, [item.id])

  useEffect(() => {
    if (slideshow) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') (zoom ? setZoom(null) : onClose())
      else if (e.key === 'ArrowRight' && index < items.length - 1) onIndex(index + 1)
      else if (e.key === 'ArrowLeft' && index > 0) onIndex(index - 1)
      else if (e.key === 'i') setShowInfo((s) => !s)
      else if (e.key === 'r') rotate()
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  })

  function rotate() {
    if (item.kind !== 'photo') return
    const next = (rotation + 90) % 360
    setRotations((r) => ({ ...r, [item.id]: next }))
    item.rotation = next // keep grids in sync when the viewer closes
    story.setRotation(item.id, next).catch(() => setRotations((r) => ({ ...r, [item.id]: rotation })))
  }

  function toggleZoom(clientX: number, clientY: number, el: HTMLElement) {
    if (zoom) return setZoom(null)
    const r = el.getBoundingClientRect()
    setZoom({ x: ((clientX - r.left) / r.width) * 100, y: ((clientY - r.top) / r.height) * 100 })
  }

  function pan(e: ReactMouseEvent<HTMLImageElement>) {
    if (!zoom) return
    const r = e.currentTarget.getBoundingClientRect()
    setZoom({ x: ((e.clientX - r.left) / r.width) * 100, y: ((e.clientY - r.top) / r.height) * 100 })
  }

  if (slideshow) {
    return <Slideshow items={items} startIndex={index} onClose={() => setSlideshow(false)} />
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed-scale fixed inset-0 z-50 flex bg-stone-950/95 text-stone-100"
      role="dialog"
      aria-modal="true"
      aria-label={item.filename}
    >
      <div
        className="relative flex-1 flex items-center justify-center overflow-hidden p-4 sm:p-10"
        onClick={onClose}
        onTouchStart={(e) => {
          touch.current = { x: e.touches[0].clientX, y: e.touches[0].clientY, t: Date.now() }
        }}
        onTouchEnd={(e) => {
          const s = touch.current
          touch.current = null
          if (!s || zoom) return
          const dx = e.changedTouches[0].clientX - s.x
          const dy = e.changedTouches[0].clientY - s.y
          if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) {
            if (dx < 0 && index < items.length - 1) onIndex(index + 1)
            if (dx > 0 && index > 0) onIndex(index - 1)
          } else if (dy > 120 && Math.abs(dy) > Math.abs(dx)) {
            onClose() // swipe down to close
          }
        }}
      >
        <AnimatePresence mode="wait">
          <motion.div
            key={item.id}
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="max-h-full max-w-full flex"
            onClick={(e) => e.stopPropagation()}
          >
            {item.kind === 'video' ? (
              <video src={originalUrl(item.id)} controls autoPlay className="max-h-[85dvh] max-w-full rounded-lg" />
            ) : (
              <img
                src={originalUrl(item.id)}
                alt={item.filename}
                draggable={false}
                onDoubleClick={(e) => toggleZoom(e.clientX, e.clientY, e.currentTarget)}
                onTouchEnd={(e) => {
                  const now = Date.now()
                  if (now - lastTap.current < 300) {
                    const t = e.changedTouches[0]
                    toggleZoom(t.clientX, t.clientY, e.currentTarget)
                  }
                  lastTap.current = now
                }}
                onMouseMove={pan}
                style={{
                  transform: `rotate(${rotation}deg) scale(${zoom ? 2.4 : 1})`,
                  transformOrigin: zoom ? `${zoom.x}% ${zoom.y}%` : 'center',
                  transition: 'transform 0.35s ease',
                }}
                className={`${sideways ? 'max-h-[min(80vw,85dvh)] max-w-[80dvh]' : 'max-h-[85dvh] max-w-full'} object-contain rounded-lg shadow-2xl ${
                  zoom ? 'cursor-zoom-out' : 'cursor-zoom-in'
                }`}
              />
            )}
          </motion.div>
        </AnimatePresence>

        <NavButton side="left" disabled={index === 0 || !!zoom} onClick={() => onIndex(index - 1)} />
        <NavButton side="right" disabled={index >= items.length - 1 || !!zoom} onClick={() => onIndex(index + 1)} />

        <div className="absolute top-3 right-3 flex flex-wrap justify-end gap-2" onClick={(e) => e.stopPropagation()}>
          {items.some((m) => m.kind === 'photo') && (
            <button onClick={() => setSlideshow(true)} className="rounded-full bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20" title="Slideshow">
              ▶ Slideshow
            </button>
          )}
          {item.kind === 'photo' && (
            <button
              onClick={rotate}
              className="rounded-full bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20"
              title="Rotate (R). Only changes how the app shows it; the file is not modified."
            >
              ⟳ Rotate
            </button>
          )}
          <button onClick={() => setShowInfo((s) => !s)} className="rounded-full bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20">
            Info
          </button>
          <button onClick={onClose} className="rounded-full bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20">
            Close
          </button>
        </div>
        <p className="pointer-events-none absolute bottom-3 inset-x-0 text-center text-xs text-white/50 tabular-nums">
          {index + 1} / {items.length}
        </p>
      </div>
      {showInfo && (
        <aside className="absolute inset-x-0 bottom-0 max-h-[55dvh] overflow-y-auto rounded-t-2xl bg-stone-950/95 p-6 text-sm md:static md:max-h-none md:w-80 md:shrink-0 md:rounded-none md:border-l md:border-white/10 md:bg-transparent">
          <h2 className="font-serif text-2xl">{formatDate(item.taken_at, true)}</h2>
          <p className="mt-2 inline-flex items-center gap-2 text-stone-300">
            <span
              className={`h-2 w-2 rounded-full ${
                item.date_confidence === 'high'
                  ? 'bg-emerald-400'
                  : item.date_confidence === 'medium'
                    ? 'bg-sky-400'
                    : 'bg-amber-400'
              }`}
            />
            {DATE_SOURCE_LABEL[item.date_source]} · {item.date_confidence} confidence
          </p>
          {detail && detail.faces.some((f) => f.person_id && !f.person_hidden) && (
            <div className="mt-5 flex flex-wrap gap-2">
              {detail.faces
                .filter((f) => f.person_id && !f.person_hidden)
                .map((f) => (
                  <a
                    key={f.id}
                    href={`#/people/${f.person_id}`}
                    onClick={onClose}
                    className="flex items-center gap-2 rounded-full bg-white/10 py-1 pl-1 pr-3 text-sm hover:bg-white/20"
                  >
                    <img src={faceUrl(f.id)} alt="" className="h-6 w-6 rounded-full object-cover" />
                    {f.person_name ?? 'Unnamed'}
                  </a>
                ))}
            </div>
          )}
          {detail?.event && (
            <a
              href={`#/events/${detail.event.id}`}
              onClick={onClose}
              className="mt-5 block rounded-xl bg-white/10 px-3 py-2 hover:bg-white/20"
            >
              <span className="block text-xs uppercase tracking-wide text-stone-400">Event</span>
              <span className="font-serif text-base">{detail.event.title}</span>
            </a>
          )}
          {detail && detail.tags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {detail.tags.map((t) => (
                <span key={t.tag} className="rounded-full bg-white/10 px-2 py-0.5 text-xs" title={`${Math.round(t.score * 100)}% sure`}>
                  {TAG_LABEL[t.tag]}
                </span>
              ))}
            </div>
          )}
          <dl className="mt-6 space-y-3">
            <Row label="File" value={item.filename} />
            {detail && <Row label="Location on disk" value={detail.path} mono />}
            {item.width && <Row label="Size" value={`${item.width} × ${item.height}${detail ? ` · ${formatBytes(detail.size)}` : ''}`} />}
            {detail?.camera && <Row label="Camera" value={detail.camera} />}
            {detail?.gps_lat != null && (
              <Row label="GPS" value={`${detail.gps_lat.toFixed(5)}, ${detail.gps_lon?.toFixed(5)}`} />
            )}
            {item.error && <Row label="Problem" value={item.error} />}
          </dl>
          {detail?.quality && (
            <div className="mt-6 border-t border-white/10 pt-5">
              <QualityBars q={detail.quality} dark />
            </div>
          )}
          {detail && detail.group_size && detail.group_size > 1 && (
            <a href="#/duplicates" className="mt-4 inline-block text-xs text-amber-300 hover:underline">
              Best of {detail.group_size} similar photos · review →
            </a>
          )}
          <p className="mt-8 text-xs text-stone-500">← → to browse · i for info · Esc to close</p>
        </aside>
      )}
    </motion.div>
  )
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-stone-500">{label}</dt>
      <dd className={`mt-0.5 text-stone-200 break-all ${mono ? 'font-mono text-xs' : ''}`}>{value}</dd>
    </div>
  )
}

function NavButton({ side, disabled, onClick }: { side: 'left' | 'right'; disabled: boolean; onClick: () => void }) {
  if (disabled) return null
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      aria-label={side === 'left' ? 'Previous' : 'Next'}
      className={`absolute top-1/2 -translate-y-1/2 ${side === 'left' ? 'left-3' : 'right-3'} h-12 w-12 rounded-full bg-white/10 text-2xl hover:bg-white/20`}
    >
      {side === 'left' ? '‹' : '›'}
    </button>
  )
}
