import type { FeatureCollection } from 'geojson'
import type { ExpressionSpecification } from 'maplibre-gl'
import { useEffect, useMemo, useRef, useState } from 'react'
import Map, {
  Layer,
  Marker,
  NavigationControl,
  Popup,
  Source,
  type MapLayerMouseEvent,
  type MapRef,
} from 'react-map-gl/maplibre'
import type { Checkpoint, Plan } from '../api'
import { formatTime, LEVEL_COLOR, LEVEL_LABEL } from '../format'

// Free vector tiles, no key needed.
const MAP_STYLE = 'https://tiles.openfreemap.org/styles/positron'
const US_VIEW = { longitude: -98.5, latitude: 39.5, zoom: 3.6 }

const levelColor: ExpressionSpecification = [
  'match',
  ['get', 'level'],
  'low',
  LEVEL_COLOR.low,
  'moderate',
  LEVEL_COLOR.moderate,
  'high',
  LEVEL_COLOR.high,
  'severe',
  LEVEL_COLOR.severe,
  'no_travel',
  LEVEL_COLOR.no_travel,
  '#64748b',
]

type Props = {
  plan: Plan | null
  selectedId: string | null
  onSelect: (id: string) => void
}

export function TripMap({ plan, selectedId, onSelect }: Props) {
  const mapRef = useRef<MapRef>(null)
  const [popup, setPopup] = useState<Checkpoint | null>(null)
  const [hovering, setHovering] = useState(false)

  // Close the popup when a new plan arrives (adjusting state during render
  // instead of in an effect avoids an extra render).
  const [shownPlan, setShownPlan] = useState(plan)
  if (plan !== shownPlan) {
    setShownPlan(plan)
    setPopup(null)
  }

  const selected = plan?.routes.find((r) => r.id === selectedId) ?? null

  // Every route's colored pieces in one source; the layers below pick out
  // the selected route or the others with a filter.
  const routeLines = useMemo<FeatureCollection>(
    () => ({
      type: 'FeatureCollection',
      features: (plan?.routes ?? []).flatMap((route) =>
        route.segments.map((segment) => ({
          type: 'Feature',
          properties: { route_id: route.id, level: segment.level, selected: route.id === selectedId },
          geometry: { type: 'LineString', coordinates: segment.coordinates },
        })),
      ),
    }),
    [plan, selectedId],
  )

  const checkpoints = useMemo<FeatureCollection>(
    () => ({
      type: 'FeatureCollection',
      features: (selected?.checkpoints ?? []).map((c, index) => ({
        type: 'Feature',
        properties: { index, level: c.level },
        geometry: { type: 'Point', coordinates: [c.lon, c.lat] },
      })),
    }),
    [selected],
  )

  // Zoom to the trip when a new plan arrives.
  useEffect(() => {
    if (!plan || !mapRef.current) return
    const coords = plan.routes.flatMap((r) => r.segments.flatMap((s) => s.coordinates))
    const lons = coords.map((c) => c[0])
    const lats = coords.map((c) => c[1])
    mapRef.current.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      {
        // on phones the legend sits on top of the map, so leave room for it
        padding: window.innerWidth < 768 ? { top: 90, bottom: 30, left: 30, right: 50 } : 60,
        duration: 800,
      },
    )
  }, [plan])

  function onClick(event: MapLayerMouseEvent) {
    const feature = event.features?.[0]
    if (!feature) {
      setPopup(null)
      return
    }
    if (feature.layer.id === 'checkpoints' && selected) {
      setPopup(selected.checkpoints[feature.properties.index as number])
    } else if (feature.layer.id === 'routes-other') {
      setPopup(null)
      onSelect(feature.properties.route_id as string)
    }
  }

  const origin = selected?.checkpoints[0]
  const destination = selected?.checkpoints.at(-1)

  return (
    <Map
      ref={mapRef}
      initialViewState={US_VIEW}
      mapStyle={MAP_STYLE}
      attributionControl={{ compact: true }}
      interactiveLayerIds={['routes-other', 'checkpoints']}
      onClick={onClick}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      cursor={hovering ? 'pointer' : 'grab'}
      style={{ width: '100%', height: '100%' }}
    >
      <NavigationControl position="top-right" showCompass={false} />

      <Source id="routes" type="geojson" data={routeLines}>
        <Layer
          id="routes-other"
          type="line"
          filter={['==', ['get', 'selected'], false]}
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': '#94a3b8', 'line-width': 4, 'line-opacity': 0.85 }}
        />
        <Layer
          id="routes-selected-casing"
          type="line"
          filter={['==', ['get', 'selected'], true]}
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': '#ffffff', 'line-width': 9 }}
        />
        <Layer
          id="routes-selected"
          type="line"
          filter={['==', ['get', 'selected'], true]}
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': levelColor, 'line-width': 5 }}
        />
      </Source>

      <Source id="checkpoints" type="geojson" data={checkpoints}>
        <Layer
          id="checkpoints"
          type="circle"
          paint={{
            'circle-color': levelColor,
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 3.5, 9, 7],
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 1.5,
          }}
        />
      </Source>

      {origin && (
        <Marker longitude={origin.lon} latitude={origin.lat} anchor="bottom">
          <Pin text="S" title="Start" />
        </Marker>
      )}
      {destination && (
        <Marker longitude={destination.lon} latitude={destination.lat} anchor="bottom">
          <Pin text="E" title="End" />
        </Marker>
      )}

      {popup && (
        <Popup
          longitude={popup.lon}
          latitude={popup.lat}
          anchor="bottom"
          offset={10}
          closeOnClick={false}
          onClose={() => setPopup(null)}
          maxWidth="280px"
        >
          <CheckpointDetails checkpoint={popup} />
        </Popup>
      )}
    </Map>
  )
}

function Pin({ text, title }: { text: string; title: string }) {
  return (
    <div
      title={title}
      className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-slate-900 text-xs font-bold text-white shadow"
    >
      {text}
    </div>
  )
}

function CheckpointDetails({ checkpoint: c }: { checkpoint: Checkpoint }) {
  return (
    <div className="text-sm text-slate-800">
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: LEVEL_COLOR[c.level] }} />
        <span className="font-semibold">{LEVEL_LABEL[c.level]}</span>
        <span className="text-slate-500">mile {Math.round(c.mile)}</span>
      </div>
      <div className="mt-1 text-xs text-slate-500">Truck arrives {formatTime(c.eta)}</div>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">
        <dt className="text-slate-500">Wind</dt>
        <dd>{c.wind_mph.toFixed(0)} mph</dd>
        <dt className="text-slate-500">Gusts</dt>
        <dd>{c.gust_mph == null ? 'n/a' : `${c.gust_mph.toFixed(0)} mph`}</dd>
        <dt className="text-slate-500">Rain</dt>
        <dd>{c.rain_in_hr.toFixed(2)} in/hr</dd>
        <dt className="text-slate-500">Snow</dt>
        <dd>{c.snow_in_hr.toFixed(2)} in/hr</dd>
      </dl>
      <p className="mt-2 border-t border-slate-100 pt-2 text-xs">{c.reason}</p>
    </div>
  )
}
