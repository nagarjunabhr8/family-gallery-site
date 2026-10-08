export type DateSource = 'exif' | 'video_meta' | 'filename' | 'mtime'
export type Confidence = 'high' | 'medium' | 'low'
export type Kind = 'photo' | 'video'

export interface MediaItem {
  id: number
  filename: string
  kind: Kind
  taken_at: string
  date_source: DateSource
  date_confidence: Confidence
  width: number | null
  height: number | null
  duration_s: number | null
  has_thumb: boolean
  error: string | null
  group_id?: number | null
  group_size?: number
}

export interface QualityScores {
  total: number
  sharpness: number
  exposure: number
  resolution: number
  faces: number
  face_score: number | null
  eyes_open: number | null
  aesthetic: number | null
  aesthetic_raw: number | null
}

export type GroupKind = 'exact' | 'near' | 'burst'

export interface GroupMember extends MediaItem {
  size: number
  rel_path: string
  is_best: boolean
  pinned: boolean
  distance: number
  quality: QualityScores | null
}

export interface DupGroup {
  id: number
  kind: GroupKind
  size: number
  taken_at: string
  best_media_id: number
  user_chosen: boolean
  members: GroupMember[]
}

export interface GroupPage {
  total: number
  counts: Partial<Record<GroupKind, number>>
  groups: DupGroup[]
}

export interface AppSettings {
  near_dup_threshold: number
  burst_threshold: number
  burst_enabled: boolean
}

export type AiStatus = Record<string, { installed: boolean; purpose: string; file: string }>

export interface Person {
  id: number
  name: string | null
  birth_date: string | null
  hidden: boolean
  cover_face_id: number | null
  face_count: number
  photo_count: number
  first_taken: string | null
  last_taken: string | null
}

export interface PeopleList {
  people: Person[]
  unassigned_faces: number
  hidden_people: number
}

export interface PersonPhoto extends MediaItem {
  face_id: number
  age: string | null
}

export interface PersonDetail extends Person {
  photos: PersonPhoto[]
}

export interface FaceItem {
  id: number
  media_id: number
  taken_at: string
  filename: string
  quality: number
  similarity?: number
  assigned_by?: 'auto' | 'user'
}

export interface FaceInPhoto {
  id: number
  x: number
  y: number
  w: number
  h: number
  person_id: number | null
  person_name: string | null
  person_hidden: boolean
}

export interface MediaDetail extends MediaItem {
  faces: FaceInPhoto[]
  quality: QualityScores | null
  path: string
  size: number
  camera: string | null
  gps_lat: number | null
  gps_lon: number | null
  sha256: string | null
  missing: boolean
  scanned_at: string
}

export interface MediaPage {
  total: number
  offset: number
  items: MediaItem[]
}

export interface Folder {
  id: number
  path: string
  enabled: boolean
  added_at: string
  last_scanned_at: string | null
  exists: boolean
  media_count: number
}

export interface ScanJob {
  id: number
  kind: 'scan' | 'analyze'
  status: 'queued' | 'running' | 'done' | 'cancelled' | 'failed' | 'interrupted'
  folder_id: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  total: number
  processed: number
  added: number
  updated: number
  unchanged: number
  missing: number
  errors: number
  message: string | null
}

export interface ScanStatus {
  active: ScanJob | null
  last: ScanJob | null
}

export interface Stats {
  total: number
  photos: number
  videos: number
  by_date_source: Partial<Record<DateSource, number>>
  by_year: { year: number; count: number }[]
  with_errors: number
  missing: number
  duplicate_groups: number
  hidden_duplicates: number
}

export interface MediaQuery {
  offset?: number
  limit?: number
  kind?: Kind
  date_source?: DateSource
  include_duplicates?: boolean
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      // non-JSON error body
    }
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

export const api = {
  folders: () => request<Folder[]>('/api/folders'),
  addFolder: (path: string) =>
    request<Folder>('/api/folders', { method: 'POST', body: JSON.stringify({ path }) }),
  removeFolder: (id: number) => request<{ media_forgotten: number }>(`/api/folders/${id}`, { method: 'DELETE' }),
  startScan: (folderId?: number) =>
    request<ScanJob>('/api/scan', { method: 'POST', body: JSON.stringify({ folder_id: folderId ?? null }) }),
  scanStatus: () => request<ScanStatus>('/api/scan/status'),
  cancelScan: () => request<{ ok: boolean }>('/api/scan/cancel', { method: 'POST' }),
  media: (q: MediaQuery) => {
    const params = new URLSearchParams()
    for (const [k, v] of Object.entries(q)) if (v !== undefined) params.set(k, String(v))
    return request<MediaPage>(`/api/media?${params}`)
  },
  mediaDetail: (id: number) => request<MediaDetail>(`/api/media/${id}`),
  stats: () => request<Stats>('/api/stats'),
  groups: (q: { kind?: GroupKind; offset?: number; limit?: number }) => {
    const params = new URLSearchParams()
    for (const [k, v] of Object.entries(q)) if (v !== undefined) params.set(k, String(v))
    return request<GroupPage>(`/api/groups?${params}`)
  },
  chooseBest: (groupId: number, mediaId: number | null) =>
    request<DupGroup>(`/api/groups/${groupId}/best`, { method: 'POST', body: JSON.stringify({ media_id: mediaId }) }),
  settings: () => request<AppSettings>('/api/settings'),
  saveSettings: (s: Partial<AppSettings>) =>
    request<{ settings: AppSettings; regroup: { groups: number; hidden: number } }>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(s),
    }),
  analyze: () => request<ScanJob>('/api/analyze', { method: 'POST' }),
  aiStatus: () => request<AiStatus>('/api/ai/status'),
  people: (includeHidden = false) => request<PeopleList>(`/api/people?include_hidden=${includeHidden}`),
  person: (id: number) => request<PersonDetail>(`/api/people/${id}`),
  updatePerson: (id: number, patch: { name?: string | null; birth_date?: string | null; hidden?: boolean }) =>
    request<Person>(`/api/people/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  mergePerson: (id: number, intoId: number) =>
    request<Person>(`/api/people/${id}/merge`, { method: 'POST', body: JSON.stringify({ into_id: intoId }) }),
  personFaces: (id: number) => request<FaceItem[]>(`/api/people/${id}/faces`),
  unassignedFaces: (offset = 0, limit = 200) =>
    request<{ total: number; faces: FaceItem[] }>(`/api/faces/unassigned?offset=${offset}&limit=${limit}`),
  assignFaces: (faceIds: number[], target: { person_id?: number | null; new_person_name?: string }) =>
    request<{ ok: boolean; person_id: number | null }>('/api/faces/assign', {
      method: 'POST',
      body: JSON.stringify({ face_ids: faceIds, ...target }),
    }),
  recluster: () =>
    request<{ assigned: number; new_people: number; unassigned: number }>('/api/people/recluster', { method: 'POST' }),
}

export const faceUrl = (id: number) => `/api/faces/${id}/crop`

export function personLabel(p: { id: number; name: string | null }): string {
  return p.name ?? `Unnamed person ${p.id}`
}

export function yearSpan(first: string | null, last: string | null): string {
  if (!first || !last) return ''
  const a = new Date(first).getFullYear()
  const b = new Date(last).getFullYear()
  return a === b ? String(a) : `${a}–${b}`
}

export const GROUP_KIND_LABEL: Record<GroupKind, string> = {
  exact: 'Exact copies',
  near: 'Look-alikes',
  burst: 'Burst shots',
}

export const thumbUrl = (id: number) => `/api/media/${id}/thumb`
export const originalUrl = (id: number) => `/api/media/${id}/original`

export const DATE_SOURCE_LABEL: Record<DateSource, string> = {
  exif: 'Camera (EXIF)',
  video_meta: 'Video metadata',
  filename: 'From filename',
  mtime: 'File modified date',
}

export function formatDate(iso: string, withTime = false): string {
  return new Date(iso).toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    ...(withTime ? { hour: 'numeric', minute: '2-digit' } : {}),
  })
}

export function formatDuration(seconds: number | null): string {
  if (!seconds) return ''
  const s = Math.round(seconds)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
