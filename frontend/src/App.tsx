import { useMutation, useQuery } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { fetchHeatmap, fetchPlan, type PlanRequest } from './api'
import { HourSlider } from './components/HourSlider'
import { Legend } from './components/Legend'
import { RouteCards } from './components/RouteCards'
import { TripForm } from './components/TripForm'
import { TripMap } from './components/TripMap'
import { WakeGate } from './components/WakeGate'
import { truckPosition } from './truck'

const MAX_HOUR = 48

export default function App() {
  return (
    <WakeGate>
      <Planner />
    </WakeGate>
  )
}

function Planner() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hour, setHour] = useState(0)
  const [showHeatmap, setShowHeatmap] = useState(true)
  const planMutation = useMutation({
    mutationFn: (request: PlanRequest) => fetchPlan(request),
    onSuccess: (plan) => {
      setSelectedId(plan.recommended_route_id)
      setHour(0)
    },
  })
  const plan = planMutation.data ?? null
  const request = planMutation.variables

  // Load the heatmap after the plan, so the backend can reuse the routes it
  // just fetched instead of asking the routing server twice.
  const heatmapQuery = useQuery({
    queryKey: ['heatmap', request],
    queryFn: ({ signal }) => fetchHeatmap(request!, signal),
    enabled: planMutation.isSuccess && !!request,
    staleTime: 10 * 60_000,
  })
  const heatmap = planMutation.isSuccess ? (heatmapQuery.data ?? null) : null

  const selected = plan?.routes.find((r) => r.id === selectedId) ?? null
  const truck = plan && selected ? truckPosition(selected, new Date(new Date(plan.depart_at).getTime() + hour * 3600_000)) : null
  const truckStatus = truck
    ? truck.arrived
      ? `Route ${selected!.id} has arrived`
      : `Route ${selected!.id} truck near mile ${Math.round(truck.mile)}`
    : null

  const onHourChange = useCallback((h: number) => setHour(h), [])

  return (
    <div className="flex h-full flex-col md:flex-row">
      <aside className="order-2 flex min-h-0 flex-1 flex-col border-slate-200 bg-slate-50 md:order-1 md:w-[400px] md:flex-none md:border-r">
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          <header>
            <h1 className="text-lg font-semibold">Truck route weather check</h1>
            <p className="text-sm text-slate-600">
              Compare 3 routes by the forecast the truck will drive into, its load and the drive
              time.
            </p>
          </header>

          <TripForm loading={planMutation.isPending} onSubmit={(request) => planMutation.mutate(request)} />

          {planMutation.isError && (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {planMutation.error.message}
            </div>
          )}

          {plan && selectedId && <RouteCards plan={plan} selectedId={selectedId} onSelect={setSelectedId} />}
        </div>
      </aside>

      <main className="relative order-1 h-[45vh] md:order-2 md:h-full md:flex-1">
        <TripMap
          plan={plan}
          selectedId={selectedId}
          onSelect={setSelectedId}
          heatmap={heatmap}
          hour={hour}
          showHeatmap={showHeatmap}
          truck={truck}
        />
        <div className="pointer-events-none absolute top-3 left-3 max-w-[calc(100%-4rem)]">
          <Legend />
        </div>
        {plan && (
          <div className="absolute right-3 bottom-8 left-3 md:right-auto md:left-1/2 md:w-[560px] md:-translate-x-1/2">
            <HourSlider
              hour={hour}
              maxHour={MAX_HOUR}
              times={heatmap?.times ?? null}
              status={truckStatus}
              showHeatmap={showHeatmap}
              onHourChange={onHourChange}
              onShowHeatmapChange={setShowHeatmap}
              error={heatmapQuery.isError ? heatmapQuery.error.message : null}
            />
          </div>
        )}
        {planMutation.isPending && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/50">
            <div className="rounded-lg bg-white px-4 py-3 text-sm shadow-md">
              Getting routes and the forecast along each one. This can take up to 30 seconds on
              the free servers.
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
