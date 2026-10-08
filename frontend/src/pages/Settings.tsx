import { AnimatePresence, motion } from 'framer-motion'
import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, formatDate } from '../api'
import type { AiStatus, AppSettings, Folder, ScanJob, ScanStatus } from '../api'

export default function Settings() {
  const [folders, setFolders] = useState<Folder[]>([])
  const [status, setStatus] = useState<ScanStatus>({ active: null, last: null })
  const [path, setPath] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refreshFolders = useCallback(() => api.folders().then(setFolders).catch((e) => setError(e.message)), [])
  const refreshStatus = useCallback(() => api.scanStatus().then(setStatus).catch(() => {}), [])

  useEffect(() => {
    refreshFolders()
    refreshStatus()
  }, [refreshFolders, refreshStatus])

  // Poll while a scan is running; refresh folder counts when it ends
  const scanning = status.active !== null
  useEffect(() => {
    if (!scanning) return
    const t = setInterval(refreshStatus, 1000)
    return () => {
      clearInterval(t)
      refreshFolders()
    }
  }, [scanning, refreshStatus, refreshFolders])

  async function addFolder(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await api.addFolder(path)
      setPath('')
      await refreshFolders()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function removeFolder(f: Folder) {
    const ok = window.confirm(
      `Remove "${f.path}" from Family Memories?\n\nThis only forgets it in the app. Your photos on disk are not touched.`,
    )
    if (!ok) return
    try {
      await api.removeFolder(f.id)
      await refreshFolders()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  async function scan(folderId?: number) {
    setError(null)
    try {
      await api.startScan(folderId)
      await refreshStatus()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-10">
      <section>
        <h1 className="font-serif text-3xl text-stone-900">Photo folders</h1>
        <p className="mt-2 text-stone-600">
          Folders are scanned recursively and only ever read. Nothing is written, moved or deleted inside them.
        </p>

        <form onSubmit={addFolder} className="mt-6 flex flex-col sm:flex-row gap-3">
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="D:\Photos\Family"
            aria-label="Folder path"
            className="flex-1 rounded-xl border border-stone-300 bg-white px-4 py-2.5 font-mono text-sm outline-none focus:border-stone-500 focus:ring-2 focus:ring-stone-200"
          />
          <button
            type="submit"
            disabled={busy || !path.trim()}
            className="rounded-xl bg-stone-800 px-5 py-2.5 text-stone-50 hover:bg-stone-700 disabled:opacity-40"
          >
            Add folder
          </button>
        </form>
        <p className="mt-2 text-xs text-stone-500">
          Tip: in File Explorer, right-click a folder → “Copy as path”, then paste here.
        </p>

        <AnimatePresence>
          {error && (
            <motion.p
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              role="alert"
              className="mt-4 rounded-xl bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-800"
            >
              {error}
            </motion.p>
          )}
        </AnimatePresence>

        <ul className="mt-6 space-y-3">
          {folders.length === 0 && (
            <li className="rounded-2xl border border-dashed border-stone-300 px-5 py-8 text-center text-stone-500">
              No folders yet. Add one above to get started.
            </li>
          )}
          {folders.map((f) => (
            <li
              key={f.id}
              className="rounded-2xl bg-white border border-stone-200 px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-3"
            >
              <div className="flex-1 min-w-0">
                <p className="font-mono text-sm text-stone-800 break-all">{f.path}</p>
                <p className="mt-1 text-xs text-stone-500">
                  {f.media_count.toLocaleString()} items ·{' '}
                  {f.last_scanned_at ? `last scanned ${formatDate(f.last_scanned_at, true)}` : 'not scanned yet'}
                  {!f.exists && <span className="ml-2 text-amber-700">· folder not found (drive unplugged?)</span>}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => scan(f.id)}
                  disabled={scanning}
                  className="rounded-lg border border-stone-300 px-3 py-1.5 text-sm hover:bg-stone-100 disabled:opacity-40"
                >
                  Scan
                </button>
                <button
                  onClick={() => removeFolder(f)}
                  disabled={scanning}
                  className="rounded-lg px-3 py-1.5 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-40"
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <DuplicateSettings scanning={scanning} onAnalyze={() => api.analyze().then(refreshStatus)} />

      <section>
        <div className="flex items-end justify-between gap-4">
          <h2 className="font-serif text-2xl text-stone-900">Scanning</h2>
          {scanning ? (
            <button
              onClick={() => api.cancelScan().then(refreshStatus)}
              className="rounded-xl border border-stone-300 px-4 py-2 text-sm hover:bg-stone-100"
            >
              Cancel scan
            </button>
          ) : (
            <button
              onClick={() => scan()}
              disabled={folders.length === 0}
              className="rounded-xl bg-stone-800 px-5 py-2 text-stone-50 hover:bg-stone-700 disabled:opacity-40"
            >
              Scan all folders
            </button>
          )}
        </div>
        <p className="mt-2 text-stone-600 text-sm">
          Re-scans are incremental: only new or changed files are processed.
        </p>
        <div className="mt-4">
          {status.active ? (
            <JobCard job={status.active} live />
          ) : status.last ? (
            <JobCard job={status.last} />
          ) : (
            <p className="text-sm text-stone-500">No scans yet.</p>
          )}
        </div>
      </section>
    </div>
  )
}

function statusLabel(job: ScanJob): string {
  const noun = job.kind === 'analyze' ? 'analysis' : 'scan'
  switch (job.status) {
    case 'queued':
      return `Waiting to start ${noun}…`
    case 'running':
      return job.kind === 'analyze' ? 'Analysing photos (quality, faces, duplicates)…' : 'Scanning folders…'
    case 'done':
      return `Last ${noun} finished`
    default:
      return `Last ${noun} ${job.status}`
  }
}

function JobCard({ job, live = false }: { job: ScanJob; live?: boolean }) {
  const pct = job.total ? Math.round((job.processed / job.total) * 100) : 0
  const stat = (label: string, value: number, tone = 'text-stone-800') => (
    <div>
      <dt className="text-xs text-stone-500">{label}</dt>
      <dd className={`text-lg font-medium tabular-nums ${tone}`}>{value.toLocaleString()}</dd>
    </div>
  )
  return (
    <div className="rounded-2xl bg-white border border-stone-200 p-5">
      <div className="flex justify-between text-sm">
        <span className="font-medium text-stone-800">{statusLabel(job)}</span>
        <span className="text-stone-500 tabular-nums">
          {job.processed.toLocaleString()} / {job.total.toLocaleString()}
          {job.finished_at && !live && ` · ${formatDate(job.finished_at, true)}`}
        </span>
      </div>
      <div className="mt-3 h-2 rounded-full bg-stone-100 overflow-hidden">
        <motion.div
          className="h-full bg-amber-600/80"
          initial={false}
          animate={{ width: `${live ? pct : job.status === 'done' ? 100 : pct}%` }}
          transition={{ ease: 'easeOut', duration: 0.4 }}
        />
      </div>
      {job.kind === 'analyze' ? (
        <dl className="mt-4 grid grid-cols-3 gap-4">
          {stat('Analysed', job.updated)}
          {stat('Already up to date', job.unchanged)}
          {stat('Problems', job.errors, job.errors ? 'text-rose-700' : undefined)}
        </dl>
      ) : (
        <dl className="mt-4 grid grid-cols-3 sm:grid-cols-5 gap-4">
          {stat('New', job.added)}
          {stat('Updated', job.updated)}
          {stat('Unchanged', job.unchanged)}
          {stat('Missing', job.missing, job.missing ? 'text-amber-700' : undefined)}
          {stat('Problems', job.errors, job.errors ? 'text-rose-700' : undefined)}
        </dl>
      )}
      {job.message && <p className="mt-4 text-sm text-amber-800 whitespace-pre-line">{job.message}</p>}
    </div>
  )
}

function DuplicateSettings({ scanning, onAnalyze }: { scanning: boolean; onAnalyze: () => void }) {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [saved, setSaved] = useState<AppSettings | null>(null)
  const [ai, setAi] = useState<AiStatus | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.settings().then((s) => {
      setSettings(s)
      setSaved(s)
    })
    api.aiStatus().then(setAi).catch(() => {})
  }, [])

  if (!settings || !saved) return null
  const dirty = JSON.stringify(settings) !== JSON.stringify(saved)

  async function save() {
    if (!settings) return
    setBusy(true)
    setNote(null)
    try {
      const res = await api.saveSettings(settings)
      setSaved(res.settings)
      setSettings(res.settings)
      setNote(
        `Regrouped: ${res.regroup.groups} duplicate groups, ${res.regroup.hidden} copies tucked away` +
          (res.events ? `, ${res.events.events} events.` : '.'),
      )
    } catch (e) {
      setNote((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  type NumKey = 'near_dup_threshold' | 'burst_threshold' | 'event_gap_hours' | 'event_gps_km' | 'event_min_photos' | 'tag_threshold'
  const slider = (key: NumKey, label: string, help: string, max: number, min = 0, step = 1, unit = '') => (
    <label className="block">
      <div className="flex justify-between text-sm">
        <span className="text-stone-800">{label}</span>
        <span className="tabular-nums text-stone-500">
          {settings[key]}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={settings[key]}
        onChange={(e) => setSettings({ ...settings, [key]: Number(e.target.value) })}
        className="mt-2 w-full accent-amber-600"
      />
      <p className="text-xs text-stone-500">{help}</p>
    </label>
  )

  return (
    <section>
      <div className="flex items-end justify-between gap-4">
        <h2 className="font-serif text-2xl text-stone-900">Duplicates &amp; quality</h2>
        <button
          onClick={onAnalyze}
          disabled={scanning}
          className="rounded-xl border border-stone-300 px-4 py-2 text-sm hover:bg-stone-100 disabled:opacity-40"
        >
          Re-analyse photos
        </button>
      </div>
      <div className="mt-4 rounded-2xl bg-white border border-stone-200 p-5 space-y-5">
        {slider(
          'near_dup_threshold',
          'Look-alike sensitivity',
          'How different two photos may be and still count as copies. 0 = only identical-looking, 8 = recommended, higher groups more.',
          32,
        )}
        <label className="flex items-center gap-2 text-sm text-stone-800">
          <input
            type="checkbox"
            checked={settings.burst_enabled}
            onChange={(e) => setSettings({ ...settings, burst_enabled: e.target.checked })}
            className="accent-amber-600"
          />
          Group burst shots taken in the same minute
        </label>
        {settings.burst_enabled &&
          slider(
            'burst_threshold',
            'Burst sensitivity',
            'For photos taken within the same minute (camera time only). Should be higher than look-alike sensitivity.',
            40,
          )}
        <h3 className="border-t border-stone-200 pt-5 font-serif text-lg text-stone-900">Events</h3>
        {slider('event_gap_hours', 'New event after a break of', 'Photos further apart than this start a new event.', 48, 1, 1, ' h')}
        {slider('event_gps_km', 'New event after travelling', 'For photos with GPS: a jump this far starts a new event.', 500, 5, 5, ' km')}
        {slider(
          'event_min_photos',
          'Smallest event',
          'Smaller groups go into a monthly “Moments” event (unless taken on a festival or family occasion).',
          10,
          1,
        )}
        {slider(
          'tag_threshold',
          'Scene tag certainty',
          'How sure the AI must be to tag a photo as birthday, temple, beach…  Lower tags more photos (with more mistakes).',
          0.7,
          0.2,
          0.05,
        )}
        <div className="flex items-center gap-3">
          <button
            onClick={save}
            disabled={!dirty || busy || scanning}
            className="rounded-xl bg-stone-800 px-5 py-2 text-sm text-stone-50 hover:bg-stone-700 disabled:opacity-40"
          >
            Apply
          </button>
          {note && <p className="text-sm text-stone-600">{note}</p>}
        </div>
      </div>

      {ai && (
        <div className="mt-4 rounded-2xl bg-white border border-stone-200 p-5">
          <h3 className="text-sm font-medium text-stone-800">Local AI models</h3>
          <p className="mt-1 text-xs text-stone-500">Run on this computer only. Nothing is uploaded.</p>
          <ul className="mt-3 space-y-1.5 text-sm">
            {Object.entries(ai).map(([key, m]) => (
              <li key={key} className="flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${m.installed ? 'bg-emerald-500' : 'bg-stone-300'}`} />
                <span className="text-stone-700">{m.purpose}</span>
                {!m.installed && <span className="text-xs text-stone-400">(not installed)</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}