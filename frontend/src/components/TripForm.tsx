import { useState } from 'react'
import type { Place, PlanRequest } from '../api'
import { PlaceInput } from './PlaceInput'

const EXAMPLES: { name: string; origin: Place; destination: Place }[] = [
  {
    name: 'Dallas → Oklahoma City',
    origin: { label: 'Dallas, Texas', lat: 32.7767, lon: -96.797 },
    destination: { label: 'Oklahoma City, Oklahoma', lat: 35.4676, lon: -97.5164 },
  },
  {
    name: 'Dallas → Denver',
    origin: { label: 'Dallas, Texas', lat: 32.7767, lon: -96.797 },
    destination: { label: 'Denver, Colorado', lat: 39.7392, lon: -104.9903 },
  },
  {
    name: 'Chicago → Denver',
    origin: { label: 'Chicago, Illinois', lat: 41.8781, lon: -87.6298 },
    destination: { label: 'Denver, Colorado', lat: 39.7392, lon: -104.9903 },
  },
]

const MAX_DAYS_AHEAD = 7

// <input type="datetime-local"> works in local time without a zone.
function toLocalInput(date: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function nextHour() {
  const date = new Date()
  date.setHours(date.getHours() + 1, 0, 0, 0)
  return date
}

type Props = {
  loading: boolean
  onSubmit: (request: PlanRequest) => void
}

export function TripForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>(null)
  const [destination, setDestination] = useState<Place | null>(null)
  const [departAt, setDepartAt] = useState(() => toLocalInput(nextHour()))
  const [load, setLoad] = useState('38000')
  const [intervalMi, setIntervalMi] = useState('auto')

  // Allowed departure range, worked out once when the form opens.
  const [range] = useState(() => {
    const now = new Date()
    return { min: toLocalInput(now), max: toLocalInput(new Date(now.getTime() + MAX_DAYS_AHEAD * 24 * 3600_000)) }
  })
  const loadLb = Number(load)
  const valid = origin && destination && departAt && load !== '' && loadLb >= 0 && loadLb <= 100_000

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!origin || !destination || !valid) return
    onSubmit({
      origin: { lat: origin.lat, lon: origin.lon },
      destination: { lat: destination.lat, lon: destination.lon },
      // the browser reads the local time and sends it as UTC
      depart_at: new Date(departAt).toISOString(),
      load_lb: loadLb,
      interval_mi: intervalMi === 'auto' ? null : Number(intervalMi),
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <PlaceInput label="From" placeholder="City or address" value={origin} onChange={setOrigin} />
      <PlaceInput label="To" placeholder="City or address" value={destination} onChange={setDestination} />

      <div className="flex flex-wrap gap-1.5">
        {EXAMPLES.map((example) => (
          <button
            key={example.name}
            type="button"
            onClick={() => {
              setOrigin(example.origin)
              setDestination(example.destination)
            }}
            className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 hover:border-slate-400"
          >
            {example.name}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <label htmlFor="depart" className="mb-1 block text-xs font-medium text-slate-600">
            Departure (your local time)
          </label>
          <input
            id="depart"
            type="datetime-local"
            required
            min={range.min}
            max={range.max}
            value={departAt}
            onChange={(event) => setDepartAt(event.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
          />
        </div>
        <div>
          <label htmlFor="load" className="mb-1 block text-xs font-medium text-slate-600">
            Load weight (lb)
          </label>
          <input
            id="load"
            type="number"
            min={0}
            max={100000}
            step={500}
            required
            value={load}
            onChange={(event) => setLoad(event.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
          />
        </div>
        <div>
          <label htmlFor="interval" className="mb-1 block text-xs font-medium text-slate-600">
            Check weather every
          </label>
          <select
            id="interval"
            value={intervalMi}
            onChange={(event) => setIntervalMi(event.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
          >
            <option value="auto">Auto (by trip length)</option>
            <option value="10">10 miles</option>
            <option value="25">25 miles</option>
            <option value="50">50 miles</option>
          </select>
        </div>
      </div>

      <button
        type="submit"
        disabled={!valid || loading}
        className="w-full rounded-lg bg-slate-900 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {loading ? 'Checking routes and forecasts…' : 'Find the safest route'}
      </button>
    </form>
  )
}
