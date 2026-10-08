import { AnimatePresence, motion } from 'framer-motion'
import { useCallback, useEffect, useState } from 'react'
import { api, formatBytes, formatDate, GROUP_KIND_LABEL, thumbUrl } from '../api'
import type { DupGroup, GroupKind, GroupMember } from '../api'
import QualityBars from '../components/QualityBars'

const PAGE = 20

export default function Duplicates() {
  const [kind, setKind] = useState<GroupKind | undefined>()
  const [groups, setGroups] = useState<DupGroup[]>([])
  const [total, setTotal] = useState(0)
  const [counts, setCounts] = useState<Partial<Record<GroupKind, number>>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(
    async (offset: number) => {
      const page = await api.groups({ kind, offset, limit: PAGE })
      setTotal(page.total)
      setCounts(page.counts)
      setGroups((prev) => (offset === 0 ? page.groups : [...prev, ...page.groups]))
    },
    [kind],
  )

  useEffect(() => {
    setLoading(true)
    load(0)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [load])

  async function choose(group: DupGroup, mediaId: number | null) {
    setError(null)
    try {
      const updated = await api.chooseBest(group.id, mediaId)
      setGroups((prev) => prev.map((g) => (g.id === updated.id ? updated : g)))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const allCount = Object.values(counts).reduce((a, b) => a + (b ?? 0), 0)
  const hidden = groups.reduce((n, g) => n + g.size - 1, 0)

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl text-stone-900">Duplicates &amp; best shots</h1>
          <p className="mt-2 text-stone-600 max-w-2xl">
            Similar photos are grouped and only the best one shows in your library. Pick a different favourite any
            time. Nothing is ever deleted; the others are just tucked away here.
          </p>
        </div>
        <div className="flex rounded-full bg-stone-200/70 p-0.5 self-start">
          {([undefined, 'exact', 'near', 'burst'] as const).map((k) => (
            <button
              key={k ?? 'all'}
              onClick={() => setKind(k)}
              className={`rounded-full px-3 py-1 text-sm ${
                kind === k ? 'bg-white text-stone-900 shadow-sm' : 'text-stone-600 hover:text-stone-900'
              }`}
            >
              {k ? GROUP_KIND_LABEL[k] : 'All'} <span className="text-stone-400">{k ? counts[k] ?? 0 : allCount}</span>
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-xl bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-800">
          {error}
        </p>
      )}

      {!loading && total === 0 && (
        <div className="mt-16 text-center text-stone-500">
          <p className="font-serif text-2xl text-stone-700">No duplicates found</p>
          <p className="mt-2 text-sm">
            Scan a folder (analysis runs automatically), or loosen the similarity settings on the Settings page.
          </p>
        </div>
      )}

      {kind === undefined && total > 0 && groups.length === total && (
        <p className="mt-6 text-sm text-stone-500">
          {total} group{total > 1 ? 's' : ''} · {hidden} extra cop{hidden === 1 ? 'y' : 'ies'} hidden from the library
        </p>
      )}

      <div className="mt-6 space-y-6">
        <AnimatePresence initial={false}>
          {groups.map((g) => (
            <GroupCard key={g.id} group={g} onChoose={(id) => choose(g, id)} />
          ))}
        </AnimatePresence>
      </div>

      {groups.length < total && (
        <div className="mt-8 text-center">
          <button
            onClick={() => load(groups.length)}
            className="rounded-xl border border-stone-300 px-5 py-2 text-sm hover:bg-stone-100"
          >
            Show more groups
          </button>
        </div>
      )}
    </div>
  )
}

function GroupCard({ group, onChoose }: { group: DupGroup; onChoose: (mediaId: number | null) => void }) {
  return (
    <motion.section
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl bg-white border border-stone-200 p-4 sm:p-5"
    >
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="rounded-full bg-stone-100 px-2.5 py-0.5 text-xs font-medium text-stone-700">
          {GROUP_KIND_LABEL[group.kind]}
        </span>
        <span className="font-serif text-lg text-stone-800">{formatDate(group.taken_at, true)}</span>
        <span className="text-sm text-stone-500">{group.size} photos</span>
        {group.user_chosen ? (
          <button onClick={() => onChoose(null)} className="ml-auto text-sm text-stone-500 hover:text-stone-800 underline">
            Let the app choose again
          </button>
        ) : (
          <span className="ml-auto text-xs text-stone-400">Best chosen automatically</span>
        )}
      </header>
      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {group.members.map((m) => (
          <MemberCard key={m.id} m={m} userChosen={group.user_chosen} onChoose={() => onChoose(m.id)} />
        ))}
      </div>
    </motion.section>
  )
}

function MemberCard({ m, userChosen, onChoose }: { m: GroupMember; userChosen: boolean; onChoose: () => void }) {
  return (
    <motion.div
      layout
      className={`rounded-xl overflow-hidden border-2 transition-colors ${
        m.is_best ? 'border-amber-500 shadow-md' : 'border-transparent bg-stone-50'
      }`}
    >
      <div className="relative aspect-[4/3] bg-stone-200">
        {m.has_thumb && (
          <img src={thumbUrl(m.id)} alt={m.filename} loading="lazy" className="h-full w-full object-cover" />
        )}
        {m.is_best && (
          <span className="absolute top-2 left-2 rounded-full bg-amber-500 px-2.5 py-0.5 text-xs font-medium text-white shadow">
            {userChosen ? '★ Your pick' : '★ Best'}
          </span>
        )}
      </div>
      <div className="p-3">
        <p className="font-mono text-xs text-stone-600 truncate" title={m.rel_path}>
          {m.rel_path}
        </p>
        <p className="mt-0.5 text-xs text-stone-400">
          {m.width} × {m.height} · {formatBytes(m.size)}
          {m.distance > 0 && ` · difference ${m.distance}`}
        </p>
        {m.quality ? (
          <div className="mt-3">
            <QualityBars q={m.quality} />
          </div>
        ) : (
          <p className="mt-3 text-xs text-stone-400">Not analysed yet</p>
        )}
        {!m.is_best && (
          <button
            onClick={onChoose}
            className="mt-4 w-full rounded-lg border border-stone-300 py-1.5 text-sm hover:bg-stone-100"
          >
            Use this one instead
          </button>
        )}
      </div>
    </motion.div>
  )
}
