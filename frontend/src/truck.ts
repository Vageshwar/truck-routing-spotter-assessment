import type { RoutePlan } from './api'

// Where the truck is on a route at a given time, by interpolating between
// the checkpoints it passes. Returns the destination once it has arrived.
export function truckPosition(route: RoutePlan, at: Date) {
  const time = at.getTime()
  const points = route.checkpoints
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i]
    const b = points[i + 1]
    const ta = new Date(a.eta).getTime()
    const tb = new Date(b.eta).getTime()
    if (time >= ta && time <= tb) {
      const t = tb > ta ? (time - ta) / (tb - ta) : 0
      return {
        lon: a.lon + (b.lon - a.lon) * t,
        lat: a.lat + (b.lat - a.lat) * t,
        mile: a.mile + (b.mile - a.mile) * t,
        arrived: false,
      }
    }
  }
  const last = points[points.length - 1]
  return { lon: last.lon, lat: last.lat, mile: last.mile, arrived: true }
}
