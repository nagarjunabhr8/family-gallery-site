import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { story } from '../api'
import type { MediaItem, OnThisDay as OTD } from '../api'
import Thumb from './Photo'

export default function OnThisDay({ onOpen }: { onOpen: (items: MediaItem[], index: number, title: string) => void }) {
  const [data, setData] = useState<OTD | null>(null)

  useEffect(() => {
    story.onThisDay().then(setData).catch(() => setData(null))
  }, [])

  if (!data || data.years.length === 0) return null
  const today = new Date(data.date + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'long' })

  return (
    <section className="animate-fade-in">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-serif text-2xl sm:text-3xl text-stone-900">
          On this {data.span === 'day' ? 'day' : 'week'}
          <span className="ml-3 text-base text-stone-500 font-sans">{today}</span>
        </h2>
      </div>
      <div className="mt-4 flex gap-5 overflow-x-auto pb-3 snap-x">
        {data.years.map((y) => (
          <motion.div
            key={y.year}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="snap-start shrink-0 w-[min(85vw,26rem)] rounded-3xl bg-paper p-3 shadow-sm ring-1 ring-stone-200"
          >
            <div className="grid grid-cols-3 grid-rows-2 gap-1.5 h-56 overflow-hidden rounded-2xl">
              {y.items.slice(0, 5).map((m, i) => (
                <button
                  key={m.id}
                  onClick={() => onOpen(y.items, i, `${y.label} · ${y.year}`)}
                  className={`overflow-hidden bg-stone-200 ${i === 0 ? 'col-span-2 row-span-2' : ''}`}
                >
                  <Thumb id={m.id} rotation={m.rotation} className="transition duration-500 hover:scale-105" />
                </button>
              ))}
            </div>
            <div className="mt-3 flex items-baseline justify-between px-1">
              <p className="font-serif text-xl text-stone-900">{y.label}</p>
              <p className="text-sm text-stone-500">
                {y.year} · {y.total} photo{y.total === 1 ? '' : 's'}
              </p>
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
