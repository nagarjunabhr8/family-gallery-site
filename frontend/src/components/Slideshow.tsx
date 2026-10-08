import { AnimatePresence, motion } from 'framer-motion'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { formatDate, musicUrl, originalUrl, story, thumbUrl } from '../api'
import type { MediaItem, MusicTrack } from '../api'
import { rotationStyle } from './Photo'

interface Props {
  items: MediaItem[]
  title?: string
  startIndex?: number
  onClose: () => void
}

// Ken Burns moves: start/end scale and drift (percent of frame)
const MOVES = [
  { from: { scale: 1.0, x: '0%', y: '0%' }, to: { scale: 1.1, x: '-2%', y: '-1.5%' } },
  { from: { scale: 1.12, x: '2%', y: '0%' }, to: { scale: 1.02, x: '-1%', y: '1%' } },
  { from: { scale: 1.02, x: '-1.5%', y: '1%' }, to: { scale: 1.12, x: '1.5%', y: '-1%' } },
  { from: { scale: 1.1, x: '0%', y: '-2%' }, to: { scale: 1.0, x: '0%', y: '1%' } },
]

function shuffle<T>(xs: T[]): T[] {
  const a = [...xs]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

export default function Slideshow({ items, title, startIndex = 0, onClose }: Props) {
  const photos = useMemo(() => items.filter((m) => m.kind === 'photo' && m.has_thumb), [items])
  const [index, setIndex] = useState(() => Math.max(0, photos.findIndex((p) => p.id === items[startIndex]?.id)))
  const [playing, setPlaying] = useState(true)
  const [seconds, setSeconds] = useState(5)
  const [controls, setControls] = useState(true)
  const [tracks, setTracks] = useState<MusicTrack[]>([])
  const [trackIndex, setTrackIndex] = useState(0)
  const [musicOn, setMusicOn] = useState(true)
  const audio = useRef<HTMLAudioElement>(null)
  const hideTimer = useRef<number | undefined>(undefined)
  const touchX = useRef<number | null>(null)
  const root = useRef<HTMLDivElement>(null)

  const item = photos[index]
  const next = useCallback(() => setIndex((i) => (i + 1) % photos.length), [photos.length])
  const prev = useCallback(() => setIndex((i) => (i - 1 + photos.length) % photos.length), [photos.length])

  // music from the user's folder, shuffled
  useEffect(() => {
    story
      .music()
      .then((m) => setTracks(shuffle(m.tracks)))
      .catch(() => setTracks([]))
  }, [])

  // advance
  useEffect(() => {
    if (!playing || photos.length < 2) return
    const t = window.setTimeout(next, seconds * 1000)
    return () => window.clearTimeout(t)
  }, [playing, index, seconds, next, photos.length])

  // preload the next photo
  useEffect(() => {
    const n = photos[(index + 1) % photos.length]
    if (n) new Image().src = originalUrl(n.id)
  }, [index, photos])

  // play/pause music with the show, fading in
  useEffect(() => {
    const el = audio.current
    if (!el || !tracks.length) return
    if (playing && musicOn) {
      el.volume = 0
      el.play().catch(() => {})
      let v = 0
      const fade = window.setInterval(() => {
        v = Math.min(0.8, v + 0.05)
        el.volume = v
        if (v >= 0.8) window.clearInterval(fade)
      }, 120)
      return () => window.clearInterval(fade)
    }
    el.pause()
  }, [playing, musicOn, tracks.length, trackIndex])

  const poke = useCallback(() => {
    setControls(true)
    window.clearTimeout(hideTimer.current)
    hideTimer.current = window.setTimeout(() => setControls(false), 2800)
  }, [])

  useEffect(() => {
    poke()
    document.body.style.overflow = 'hidden'
    const onKey = (e: KeyboardEvent) => {
      poke()
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowRight') next()
      else if (e.key === 'ArrowLeft') prev()
      else if (e.key === ' ') {
        e.preventDefault()
        setPlaying((p) => !p)
      } else if (e.key === 'm') setMusicOn((m) => !m)
      else if (e.key === 'f') toggleFullscreen()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      window.clearTimeout(hideTimer.current)
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
    }
  }, [next, prev, onClose, poke])

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
    else root.current?.requestFullscreen().catch(() => {})
  }

  if (!item) {
    return (
      <div className="fixed-scale fixed inset-0 z-50 flex items-center justify-center bg-stone-950 text-stone-200">
        <p>No photos to show.</p>
        <button onClick={onClose} className="ml-4 underline">Close</button>
      </div>
    )
  }

  const move = MOVES[index % MOVES.length]
  const track = tracks[trackIndex]

  return (
    <div
      ref={root}
      className={`fixed-scale fixed inset-0 z-50 overflow-hidden bg-stone-950 text-stone-100 select-none ${controls ? '' : 'cursor-none'}`}
      onMouseMove={poke}
      onClick={poke}
      onTouchStart={(e) => {
        touchX.current = e.touches[0].clientX
        poke()
      }}
      onTouchEnd={(e) => {
        if (touchX.current === null) return
        const dx = e.changedTouches[0].clientX - touchX.current
        if (Math.abs(dx) > 50) (dx < 0 ? next : prev)()
        touchX.current = null
      }}
      role="dialog"
      aria-label="Slideshow"
    >
      <AnimatePresence initial={false}>
        <motion.div
          key={item.id}
          className="absolute inset-0"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 1.4, ease: 'easeInOut' }}
        >
          {/* soft blurred backdrop from the same photo */}
          <img
            src={thumbUrl(item.id)}
            alt=""
            className="absolute inset-0 h-full w-full scale-110 object-cover opacity-50 blur-2xl"
            style={rotationStyle(item.rotation, false)}
          />
          <div className="absolute inset-0 bg-black/30" />
          <motion.div
            className="absolute inset-0 flex items-center justify-center p-4 sm:p-10"
            initial={move.from}
            animate={playing ? move.to : move.from}
            transition={{ duration: seconds + 1.6, ease: 'linear' }}
          >
            <img
              src={originalUrl(item.id)}
              alt={item.filename}
              className="max-h-full max-w-full rounded-md object-contain shadow-2xl"
              style={rotationStyle(item.rotation, false)}
            />
          </motion.div>
        </motion.div>
      </AnimatePresence>

      {/* caption */}
      <AnimatePresence mode="wait">
        <motion.div
          key={`cap-${item.id}`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ delay: 0.6, duration: 0.8 }}
          className="pointer-events-none absolute bottom-24 left-6 sm:left-10 drop-shadow-lg"
        >
          <p className="font-serif text-2xl sm:text-4xl italic text-white/95">{formatDate(item.taken_at)}</p>
        </motion.div>
      </AnimatePresence>

      {/* chrome */}
      <motion.div
        animate={{ opacity: controls ? 1 : 0 }}
        transition={{ duration: 0.4 }}
        className={`absolute inset-0 ${controls ? '' : 'pointer-events-none'}`}
      >
        <div className="absolute top-0 inset-x-0 flex items-start justify-between bg-gradient-to-b from-black/50 to-transparent p-4 sm:p-6">
          <div>
            {title && <p className="font-serif text-xl sm:text-2xl">{title}</p>}
            <p className="text-xs text-white/70 tabular-nums">
              {index + 1} / {photos.length}
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={toggleFullscreen} className="rounded-full bg-white/15 px-3 py-1.5 text-sm hover:bg-white/25" title="Fullscreen (F)">
              ⛶
            </button>
            <button onClick={onClose} className="rounded-full bg-white/15 px-3 py-1.5 text-sm hover:bg-white/25" title="Close (Esc)">
              Close
            </button>
          </div>
        </div>

        <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/60 to-transparent p-4 sm:p-6">
          <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-center gap-2 sm:gap-3">
            <button onClick={prev} aria-label="Previous" className="h-10 w-10 rounded-full bg-white/15 text-xl hover:bg-white/25">‹</button>
            <button
              onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? 'Pause' : 'Play'}
              className="h-12 w-12 rounded-full bg-white text-stone-900 text-lg hover:bg-white/90"
            >
              {playing ? '❚❚' : '▶'}
            </button>
            <button onClick={next} aria-label="Next" className="h-10 w-10 rounded-full bg-white/15 text-xl hover:bg-white/25">›</button>
            <select
              value={seconds}
              onChange={(e) => setSeconds(Number(e.target.value))}
              aria-label="Seconds per photo"
              className="rounded-full bg-white/15 px-3 py-2 text-sm text-white [&>option]:text-stone-900"
            >
              {[3, 5, 8, 12].map((s) => (
                <option key={s} value={s}>{s}s per photo</option>
              ))}
            </select>
            {tracks.length > 0 ? (
              <div className="flex items-center gap-2 rounded-full bg-white/15 py-1 pl-3 pr-1 text-sm">
                <button onClick={() => setMusicOn((m) => !m)} title="Music on/off (M)">
                  {musicOn ? '♫' : '♪̸'}
                </button>
                <span className="max-w-40 truncate text-white/85">{track?.title}</span>
                <button
                  onClick={() => setTrackIndex((t) => (t + 1) % tracks.length)}
                  className="rounded-full px-2 py-1 hover:bg-white/20"
                  title="Next song"
                >
                  ⏭
                </button>
              </div>
            ) : (
              <a href="#/settings" onClick={onClose} className="rounded-full bg-white/10 px-3 py-2 text-xs text-white/70 hover:bg-white/20">
                Add a music folder in Settings
              </a>
            )}
          </div>
        </div>
      </motion.div>

      {track && (
        <audio
          ref={audio}
          src={musicUrl(track.id)}
          onEnded={() => setTrackIndex((t) => (t + 1) % tracks.length)}
          preload="auto"
        />
      )}
    </div>
  )
}
