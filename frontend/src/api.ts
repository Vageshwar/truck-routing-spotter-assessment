// Types and calls for the Django API. The shapes mirror backend/planner/plan.py.

export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type Level = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'

export type Place = { label: string; lat: number; lon: number }

export type Checkpoint = {
  mile: number
  lat: number
  lon: number
  eta: string
  level: Level
  reason: string
  wind_mph: number
  gust_mph: number | null
  rain_in_hr: number
  snow_in_hr: number
}

export type Segment = { level: Level; coordinates: [number, number][] }

export type RoutePlan = {
  id: string
  source: 'valhalla' | 'valhalla-via' | 'osrm'
  rank: number
  distance_mi: number
  duration_s: number
  arrive_at: string
  miles_by_level: Record<Level, number>
  avg_risk: number
  worst_level: Level
  lost_on: { criterion: string; value: number; best: number } | null
  segments: Segment[]
  checkpoints: Checkpoint[]
}

export type Plan = {
  depart_at: string
  load_lb: number
  interval_mi: number
  gross_weight_lb: number
  over_legal_weight: boolean
  recommended_route_id: string
  all_routes_no_travel: boolean
  routes: RoutePlan[]
}

export type PlanRequest = {
  origin: { lat: number; lon: number }
  destination: { lat: number; lon: number }
  depart_at: string
  load_lb: number
  interval_mi: number | null
}

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, init)
  } catch {
    throw new ApiError('Could not reach the server. Check your connection and try again.')
  }
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(errorMessage(data) ?? `Request failed (${response.status})`)
  }
  return data as T
}

// DRF errors are either {"detail": "..."} or {"field": ["message", ...]}.
function errorMessage(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null
  const record = data as Record<string, unknown>
  if (typeof record.detail === 'string') return record.detail
  const messages = Object.values(record)
    .flat()
    .filter((m): m is string => typeof m === 'string')
  return messages.length ? messages.join(' ') : null
}

export function checkHealth(signal?: AbortSignal) {
  return request<{ status: string }>('/api/health', { signal })
}

export function searchPlaces(query: string, signal?: AbortSignal) {
  return request<Place[]>(`/api/geocode?q=${encodeURIComponent(query)}`, { signal })
}

export function fetchPlan(body: PlanRequest) {
  return request<Plan>('/api/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
