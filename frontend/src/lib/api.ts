const BASE = '/api'

// ── Types ────────────────────────────────────────────────────────────────────

export interface Run {
  run_id: string
  status: string
  started_at: string
  completed_at: string | null
  time_window_start: string
  time_window_end: string
  items_collected: number
  items_matched: number
  leads_written: number
  estimated_cost_usd: number
  stop_requested: boolean
}

export interface EvidencePost {
  item_id: string
  source: 'reddit' | 'facebook'
  subreddit: string
  text: string
  url: string
}

export interface Lead {
  id: number
  source: 'reddit' | 'facebook'
  username: string
  profile_url: string | null
  primary_event_id: string
  other_event_ids: string | null
  top_confidence: number
  user_summary: string | null
  evidence_excerpts: string[]
  evidence_urls: string[]
  evidence_posts: EvidencePost[]
  status: string
  reviewer_feedback: string | null
  notes: string | null
}

export interface Event {
  event_id: string
  title: string
  city: string
  tags: string[]
  start_time: string
  end_time: string
  capacity: number | null
}

export interface SSEUpdate {
  run_id: string
  status: string
  items_collected: number
  items_matched: number
  leads_found: number
  estimated_cost_usd: number
  budget_status: 'OK' | 'YELLOW' | 'WARNING' | 'DEGRADED'
  errors: number
}

export interface LeadPatch {
  status?: string
  reviewer_feedback?: string
  notes?: string
}

// ── Fetch helpers ─────────────────────────────────────────────────────────────

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
  return res.json()
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`)
  return res.json()
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`PATCH ${path} → ${res.status}`)
  return res.json()
}

// ── API functions ─────────────────────────────────────────────────────────────

export const api = {
  // Runs
  getRuns: (limit = 50, status?: string) => {
    const q = new URLSearchParams({ limit: String(limit) })
    if (status) q.set('status', status)
    return get<Run[]>(`/runs?${q}`)
  },
  getRun: (runId: string) => get<Run>(`/runs/${runId}`),
  triggerRun: (params?: {
    time_window_hours?: number
    start_date?: string
    end_date?: string
    max_items?: number
    max_queries?: number
    max_cost_usd?: number
  }) => {
    const q = new URLSearchParams()
    if (params?.time_window_hours) q.set('time_window_hours', String(params.time_window_hours))
    if (params?.start_date) q.set('start_date', params.start_date)
    if (params?.end_date) q.set('end_date', params.end_date)
    if (params?.max_items) q.set('max_items', String(params.max_items))
    if (params?.max_queries) q.set('max_queries', String(params.max_queries))
    if (params?.max_cost_usd) q.set('max_cost_usd', String(params.max_cost_usd))
    const qs = q.toString()
    return post<{ run_id: string; status: string }>(`/runs${qs ? '?' + qs : ''}`)
  },
  stopRun: (runId: string) => post<{ run_id: string; message: string }>(`/runs/${runId}/stop`),

  // Leads
  getLeads: (params?: {
    confidence_min?: number
    status?: string
    source?: 'reddit' | 'facebook'
    event_id?: string
    username?: string
    limit?: number
    skip?: number
  }) => {
    const q = new URLSearchParams()
    if (params?.confidence_min != null) q.set('confidence_min', String(params.confidence_min))
    if (params?.status) q.set('status', params.status)
    if (params?.source) q.set('source', params.source)
    if (params?.event_id) q.set('event_id', params.event_id)
    if (params?.username) q.set('username', params.username)
    if (params?.limit != null) q.set('limit', String(params.limit))
    if (params?.skip != null) q.set('skip', String(params.skip))
    return get<Lead[]>(`/leads?${q}`)
  },
  patchLead: (id: number, body: LeadPatch) => patch<Lead>(`/leads/${id}`, body),

  // Events
  getEvents: () => get<Event[]>('/events'),
}
