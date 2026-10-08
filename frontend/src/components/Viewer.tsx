import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { api, DATE_SOURCE_LABEL, faceUrl, formatBytes, formatDate, originalUrl } from '../api'
import type { MediaDetail, MediaItem } from '../api'
import QualityBars from './QualityBars'

interface Props {
  items: MediaItem[]
  index: number
  onIndex: (i: number) => void
  onClose: () => void
}

export default function Viewer({ items, index, onIndex, onClose }: Props) {
  const item = items[index]
  const [detail, setDetail] = useState<MediaDetail | null>(null)
  const [showInfo, setShowInfo] = useState(true)

  useEffect(() => {
    let cancelled = false
    setDetail(null)
    api.mediaDetail(item.id).then((d) => !cancelled && setDetail(d))
    return () => {
      cancelled = true
    }
  }, [item.id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowRight' && index < items.length - 1) onIndex(index + 1)
      else if (e.key === 'ArrowLeft' && index > 0) onIndex(index - 1)
      else if (e.key === 'i') setShowInfo((s) => !s)
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [index, items.length, onIndex, onClose])

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex bg-stone-950/95 text-stone-100"
      role="dialog"
      aria-modal="true"
      aria-label={item.filename}
    >
      <div className="relative flex-1 flex items-center justify-center p-4 sm:p-10" onClick={onClose}>
        <AnimatePresence mode="wait">
          <motion.div
            key={item.id}
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="max-h-full max-w-full flex"
            onClick={(e) => e.stopPropagation()}
          >
            {item.kind === 'video' ? (
              <video src={originalUrl(item.id)} controls autoPlay className="max-h-[85vh] max-w-full rounded-lg" />
            ) : (
              <img
                src={originalUrl(item.id)}
                alt={item.filename}
                className="max-h-[85vh] max-w-full object-contain rounded-lg shadow-2xl"
              />
            )}
          </motion.div>
        </AnimatePresence>

        <NavButton side="left" disabled={index === 0} onClick={() => onIndex(index - 1)} />
        <NavButton side="right" disabled={index >= items.length - 1} onClick={() => onIndex(index + 1)} />

        <div className="absolute top-3 right-3 flex gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation()
              setShowInfo((s) => !s)
            }}
            className="rounded-full bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20"
          >
            Info
          </button>
          <button onClick={onClose} className="rounded-full bg-white/10 px-3 py-1.5 text-sm hover:bg-white/20">
            Close
          </button>
        </div>
      </div>

      {showInfo && (
        <aside className="hidden md:block w-80 shrink-0 overflow-y-auto border-l border-white/10 p-6 text-sm">
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
