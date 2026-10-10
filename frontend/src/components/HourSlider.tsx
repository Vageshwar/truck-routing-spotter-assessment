import { useEffect, useState } from 'react'
import { formatTime } from '../format'

const PLAY_STEP_MS = 400

type Props = {
  hour: number
  maxHour: number
  times: string[] | null // null while the heatmap is loading
  status: string | null // e.g. where the truck is at this hour
  showHeatmap: boolean
  onHourChange: (hour: number) => void
  onShowHeatmapChange: (show: boolean) => void
  error: string | null
}

export function HourSlider({
  hour,
  maxHour,
  times,
  status,
  showHeatmap,
  onHourChange,
  onShowHeatmapChange,
  error,
}: Props) {
  const [playing, setPlaying] = useState(false)

  // Step through the hours; stop at the end.
  useEffect(() => {
    if (!playing) return
    const timer = setTimeout(() => {
      if (hour >= maxHour) setPlaying(false)
      else onHourChange(hour + 1)
    }, PLAY_STEP_MS)
    return () => clearTimeout(timer)
  }, [playing, hour, maxHour, onHourChange])

  const ready = times !== null

  return (
    <div className="rounded-xl bg-white/95 p-3 shadow-lg">
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={!ready}
          onClick={() => {
            if (!playing && hour >= maxHour) onHourChange(0)
            setPlaying(!playing)
          }}
          aria-label={playing ? 'Pause' : 'Play forecast'}
          className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-slate-900 text-white hover:bg-slate-700 disabled:bg-slate-300"
        >
          {playing ? (
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
              <rect x="2" y="1" width="3" height="10" fill="currentColor" />
              <rect x="7" y="1" width="3" height="10" fill="currentColor" />
            </svg>
          ) : (
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
              <path d="M3 1 L11 6 L3 11 Z" fill="currentColor" />
            </svg>
          )}
        </button>
        <input
          type="range"
          min={0}
          max={maxHour}
          step={1}
          value={hour}
          disabled={!ready}
          onChange={(event) => {
            setPlaying(false)
            onHourChange(Number(event.target.value))
          }}
          aria-label="Hours after departure"
          aria-valuetext={times ? `Departure plus ${hour} hours, ${formatTime(times[hour])}` : undefined}
          className="h-2 w-full cursor-pointer accent-slate-900 disabled:cursor-not-allowed"
        />
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs">
        <div className="text-slate-700">
          {error ? (
            <span className="text-red-700">Heatmap unavailable: {error}</span>
          ) : ready ? (
            <>
              <span className="font-semibold">+{hour} h</span>
              <span className="text-slate-500"> · {formatTime(times[hour])}</span>
              {status && <span className="text-slate-500"> · {status}</span>}
            </>
          ) : (
            <span className="text-slate-500">Loading the 48 hour forecast around the routes…</span>
          )}
        </div>
        <label className="flex items-center gap-1.5 text-slate-600">
          <input
            type="checkbox"
            checked={showHeatmap}
            onChange={(event) => onShowHeatmapChange(event.target.checked)}
            className="accent-slate-900"
          />
          Weather heatmap
        </label>
      </div>
    </div>
  )
}
