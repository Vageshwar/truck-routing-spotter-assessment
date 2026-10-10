import type { Level, RoutePlan } from './api'

export const LEVELS: Level[] = ['low', 'moderate', 'high', 'severe', 'no_travel']

export const LEVEL_LABEL: Record<Level, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
}

export const LEVEL_COLOR: Record<Level, string> = {
  low: '#16a34a',
  moderate: '#eab308',
  high: '#f97316',
  severe: '#dc2626',
  no_travel: '#7e22ce',
}

export const SOURCE_LABEL: Record<RoutePlan['source'], string> = {
  valhalla: 'Truck route',
  'valhalla-via': 'Truck route (detour)',
  osrm: 'Car route (fallback)',
}

const timeFormat = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
})

export function formatTime(iso: string) {
  return timeFormat.format(new Date(iso))
}

export function formatDuration(seconds: number) {
  const minutes = Math.round(seconds / 60)
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h ? `${h} h ${m} min` : `${m} min`
}

export function formatMiles(miles: number) {
  return `${Math.round(miles).toLocaleString()} mi`
}

// Why a route ranked below the recommended one, in plain words.
export function lostOnText(lost: NonNullable<RoutePlan['lost_on']>) {
  const { criterion, value, best } = lost
  if (criterion === 'travel time (s)') {
    return `Same risk, but ${formatDuration(value - best)} slower`
  }
  if (criterion === 'average risk') {
    return `Higher average risk (${value.toFixed(2)} vs ${best.toFixed(2)})`
  }
  if (criterion.startsWith('tie')) return 'Tied with the recommended route'
  return `More ${criterion} (${formatMiles(value)} vs ${formatMiles(best)})`
}
