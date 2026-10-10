import type { Plan, RoutePlan } from '../api'
import {
  formatDuration,
  formatMiles,
  formatTime,
  LEVEL_COLOR,
  LEVEL_LABEL,
  LEVELS,
  lostOnText,
  SOURCE_LABEL,
} from '../format'

type Props = {
  plan: Plan
  selectedId: string
  onSelect: (id: string) => void
}

export function RouteCards({ plan, selectedId, onSelect }: Props) {
  const ranked = [...plan.routes].sort((a, b) => a.rank - b.rank)

  return (
    <div className="space-y-3">
      {plan.all_routes_no_travel && (
        <div role="alert" className="rounded-lg border border-purple-300 bg-purple-50 p-3 text-sm text-purple-900">
          <strong>All routes cross unsafe weather.</strong> Consider delaying departure. The route
          marked recommended has the fewest No Travel miles.
        </div>
      )}
      {plan.over_legal_weight && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          With an empty truck of about 35,000 lb, this load puts the gross weight at{' '}
          {plan.gross_weight_lb.toLocaleString()} lb, over the 80,000 lb US federal limit.
        </div>
      )}
      <p className="text-xs text-slate-500">
        Weather checked every {plan.interval_mi} miles at the time the truck gets there. Ranked
        by No Travel miles, then Severe, then High, then average risk, then time.
      </p>
      {ranked.map((route) => (
        <RouteCard
          key={route.id}
          route={route}
          recommended={route.id === plan.recommended_route_id}
          selected={route.id === selectedId}
          onSelect={() => onSelect(route.id)}
        />
      ))}
    </div>
  )
}

function RouteCard({
  route,
  recommended,
  selected,
  onSelect,
}: {
  route: RoutePlan
  recommended: boolean
  selected: boolean
  onSelect: () => void
}) {
  const hasNoTravel = route.miles_by_level.no_travel > 0

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`w-full rounded-xl border bg-white p-4 text-left transition ${
        selected ? 'border-slate-900 ring-2 ring-slate-900/10' : 'border-slate-200 hover:border-slate-400'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold">Route {route.id}</span>
          {recommended && (
            <span className="rounded-full bg-emerald-600 px-2 py-0.5 text-xs font-medium text-white">
              Recommended
            </span>
          )}
        </div>
        <span className="text-xs text-slate-500">{SOURCE_LABEL[route.source]}</span>
      </div>

      {hasNoTravel && (
        <div className="mt-2 rounded-md bg-purple-100 px-2 py-1 text-xs font-semibold text-purple-900">
          ⛔ Hazardous: crosses No Travel conditions
        </div>
      )}

      <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
        <Stat label="Distance" value={formatMiles(route.distance_mi)} />
        <Stat label="Drive time" value={formatDuration(route.duration_s)} />
        <Stat label="Arrives" value={formatTime(route.arrive_at)} />
      </div>

      <RiskBar route={route} />

      <dl className="mt-2 grid grid-cols-4 gap-1 text-xs">
        {(['no_travel', 'severe', 'high'] as const).map((level) => (
          <div key={level}>
            <dt className="text-slate-500">{LEVEL_LABEL[level]}</dt>
            <dd className="font-medium">{formatMiles(route.miles_by_level[level])}</dd>
          </div>
        ))}
        <div>
          <dt className="text-slate-500">Avg risk</dt>
          <dd className="font-medium">{route.avg_risk.toFixed(2)} / 4</dd>
        </div>
      </dl>

      {route.lost_on && (
        <p className="mt-2 text-xs text-slate-600">
          <span className="font-medium">Ranked lower:</span> {lostOnText(route.lost_on)}
        </p>
      )}
    </button>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  )
}

// Share of the route's miles at each risk level.
function RiskBar({ route }: { route: RoutePlan }) {
  const total = route.distance_mi || 1
  return (
    <div className="mt-3 flex h-2.5 overflow-hidden rounded-full bg-slate-100" aria-hidden>
      {LEVELS.map((level) => {
        const share = (route.miles_by_level[level] / total) * 100
        return share > 0 ? (
          <div key={level} style={{ width: `${share}%`, background: LEVEL_COLOR[level] }} />
        ) : null
      })}
    </div>
  )
}
