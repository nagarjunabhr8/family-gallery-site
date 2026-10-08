import type { QualityScores } from '../api'

interface Props {
  q: QualityScores
  dark?: boolean
}

export default function QualityBars({ q, dark = false }: Props) {
  const rows: [string, number | null, string?][] = [
    ['Sharpness', q.sharpness],
    ['Exposure', q.exposure],
    ['Resolution', q.resolution],
    [
      'Faces',
      q.face_score,
      q.faces ? `${q.faces} face${q.faces > 1 ? 's' : ''}${q.eyes_open != null ? ` · eyes open ${Math.round(q.eyes_open * 100)}%` : ''}` : 'none',
    ],
    ['Aesthetic', q.aesthetic, q.aesthetic_raw != null ? `${q.aesthetic_raw.toFixed(1)} / 10` : 'model not installed'],
  ]
  const label = dark ? 'text-stone-400' : 'text-stone-500'
  const track = dark ? 'bg-white/10' : 'bg-stone-200'
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className={`text-3xl font-serif ${dark ? 'text-stone-100' : 'text-stone-900'}`}>{Math.round(q.total)}</span>
        <span className={`text-xs ${label}`}>quality score / 100</span>
      </div>
      <dl className="mt-3 space-y-2">
        {rows.map(([name, value, note]) => (
          <div key={name}>
            <div className={`flex justify-between text-xs ${label}`}>
              <dt>{name}</dt>
              <dd>{note ?? (value != null ? Math.round(value * 100) : '—')}</dd>
            </div>
            <div className={`mt-1 h-1.5 rounded-full ${track} overflow-hidden`}>
              {value != null && (
                <div className="h-full rounded-full bg-amber-600/80" style={{ width: `${Math.round(value * 100)}%` }} />
              )}
            </div>
          </div>
        ))}
      </dl>
    </div>
  )
}
