# Weather-Aware Truck Routing

A React + Django app that helps a truck driver pick the safest route between two places, based on the weather forecast along the way, the load weight and the travel time.

This is my submission for the Spotter Full Stack Developer assessment.

**Live app:** https://truck-routing-spotter-assessment.vercel.app
**API:** https://truck-routing-api-cpdh.onrender.com/api/health
**Walkthrough video:** https://www.loom.com/share/4f715316a7b14935abf52fc33fb3817c

The API runs on Render's free tier. If nobody has used it for a while it may need about a minute to wake up; the app shows a waiting screen while that happens.

## Status

- [x] Risk rules, load rules and route ranking, with tests
- [x] Routing (3 options), checkpoints along each route and ETAs
- [x] Weather at each checkpoint and the `/api/plan` endpoint
- [x] Frontend: form, route cards, map with routes and checkpoints
- [x] Weather heatmap with the 0 to 48 hour slider
- [x] Deploy (Vercel + Render)
- [x] Loom walkthrough

## Problem statement

Build a React + Django web app that helps a truck driver choose the safest route based on weather, load weight and travel time.

The user enters:

- Origin and destination
- Departure date and time
- Load weight

The app should:

- Generate 3 route options using a routing API.
- Sample weather every 10 / 25 / 50 miles, using the truck's estimated arrival time at each checkpoint.
- Calculate weather risk using the provided risk and load rules.
- Recommend the best route, balancing weather risk and travel time.
- Show all routes, checkpoints, risk levels, ETAs and route summaries on a map.
- Show a weather heatmap along the trip corridor with a 0 to 48 hour forecast slider.

Third party APIs can be used for routing, geocoding and weather. No need to build a routing engine.

**Risk rules** (per checkpoint):

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind | <25 mph | 25 to 34 | 35 to 44 | 45 to 54 | ≥55 mph |
| Rain | <0.10 in/hr | 0.10 to 0.25 | 0.25 to 0.50 | 0.50 to 1.00 | >1.00 |
| Snow | <0.5 in/hr | 0.5 to 1.0 | 1.0 to 2.0 | 2.0 to 3.0 | >3.0 |

**Load rules:**

- ≥55 mph wind: No Travel for any load
- 45 to 54 mph wind and more than 30,000 lb: No Travel
- 35 to 44 mph wind and more than 40,000 lb: Severe

**Route recommendation**, in order of preference:

1. Fewest Severe miles
2. Fewest High miles
3. Lowest average risk
4. Shortest travel time

Grading: 40% routes, weather, risk and recommendation logic. 35% UI, map and heatmap smoothness and performance. 10% code quality. 5% docs and walkthrough. The brief asks to prioritize correctness and clarity over extra features.

## How it works

1. The user picks an origin and destination (autocomplete), a departure time and a load weight.
2. The backend asks a truck routing engine for 3 routes.
3. Along each route it places checkpoints every 10, 25 or 50 miles, plus the origin and destination, and works out when the truck reaches each one.
4. For each checkpoint it gets the forecast for the hour the truck arrives there and classifies wind, rain and snow with the rules above.
5. Each checkpoint stands for a stretch of road, so the app adds up Severe, High and other miles per route, and ranks the routes.
6. The map shows all three routes, colored checkpoints with their ETA and reason, and a heatmap of forecast risk around the routes that you can scrub from 0 to 48 hours after departure.

### Services (all free, no paid keys)

| Need | Service | Why |
|---|---|---|
| Routing | [Valhalla](https://valhalla.github.io/valhalla/) public server, `truck` profile | Free, no key, truck aware, returns alternative routes for long trips. OSRM is the fallback. |
| Geocoding | [Photon](https://photon.komoot.io) | Free and built for search as you type. Nominatim's policy does not allow autocomplete. |
| Weather | [Open-Meteo](https://open-meteo.com) | Free, no key, hourly forecast, many locations in one request, returns mph and inches directly. |
| Map | MapLibre GL + OpenFreeMap tiles | WebGL, so the heatmap stays smooth when the slider moves. |

### Stack

- Backend: Django 5, Django REST Framework, httpx, pytest. No database models, only a cache.
- Frontend: Vite, React, TypeScript, TanStack Query, react-map-gl with MapLibre, Tailwind.
- Hosting: Vercel for the frontend, Render free tier for the backend.

## Decisions and assumptions

Before writing any code I went through the brief question by question and wrote down how I read each part that was unclear. These are the calls I made.

### Risk rules

- **Boundaries.** The table's ranges touch at the edges (0.25 in/hr rain appears in both Moderate and High). Each band includes its lower bound and excludes its upper bound, so 25 mph is Moderate and 0.25 in/hr is High. Values are treated as continuous, so 34.6 mph is Moderate.
- **No Travel for rain and snow is strict.** The brief writes ">1.00" and ">3.0", so exactly 1.00 in/hr rain or 3.0 in/hr snow is still Severe. Wind No Travel is "≥55", so 55 mph is No Travel.
- **One level per checkpoint.** The checkpoint takes the worst of wind, rain and snow, after the load rules. I don't invent combined rules (like wind plus snow) that the brief doesn't give.
- **Load rules use a strict "more than".** Exactly 30,000 lb at 50 mph stays Severe. 30,001 lb is No Travel. The load rules can only raise the wind level, never lower it.
- **Load weight means payload in pounds**, as the user types it.
- **Sustained wind, not gusts.** The table says "Wind", and thresholds like these normally refer to sustained wind. Gusts are shown in the checkpoint popup for information.

### Sampling and timing

- **"Every 10 / 25 / 50 miles"** can mean either a setting the user picks or a spacing that grows with trip length. I support both: the default depends on trip length (under 300 mi uses 10, up to 1,000 mi uses 25, longer uses 50) and the user can change it.
- **Weather at arrival time.** Each checkpoint uses the forecast for the hour the truck gets there, not the departure hour. A 14:37 ETA uses the 14:00 to 15:00 forecast hour, which matches the "in/hr" units. Open-Meteo stamps rain and snow with the end of the hour they add up, so that hour is the 15:00 record.
- **One spacing for all three routes.** The default spacing comes from the main route's length and is used for every route, so they are compared on the same terms.
- **ETAs come from the routing engine's own segment times.** Driver hours of service rules (11 hours driving, then a 10 hour break) are not modeled. That would be a good next step.
- **Departure window.** Departures from now up to 7 days ahead. This keeps every checkpoint and the 48 hour slider inside the forecast range. Past departures are blocked because forecasts don't cover the past.
- **Time zones.** Everything is UTC internally. Times are shown in the browser's local time with the zone label.

### Route recommendation

- **No Travel comes first.** The brief's list starts at "Fewest Severe miles" and never mentions No Travel. Read literally, a route with 5 No Travel miles and no Severe miles would beat a route with 1 Severe mile. I added "Fewest No Travel miles" as rule zero.
- **Strict order, no tolerances.** The brief gives an ordered list, so one fewer Severe mile beats any amount of saved time, and travel time only decides when everything above it ties. I considered a small tolerance to absorb noise from checkpoint spacing, but the brief doesn't ask for one, and for a safety tool choosing more Severe weather to save time is the wrong default. Adding one later would be a small change.
- **Miles per checkpoint use a midpoint split.** Each checkpoint covers half the gap back to the previous checkpoint and half the gap on to the next. Every mile of the route is counted exactly once, and the shorter last stretch to the destination is handled naturally.
- **Average risk is weighted by miles**, with Low = 0, Moderate = 1, High = 2, Severe = 3, No Travel = 4. A cluster of checkpoints near a city doesn't count more than one long open stretch.
- **Every result is explained.** Each checkpoint has a reason (for example "Wind 47 mph with 38,000 lb load (over 30,000 lb) -> No Travel"), and each losing route records the rule it lost on.
- **Unsafe routes are flagged.** Any route with No Travel miles gets a clear warning badge. If all three routes cross No Travel weather, the app still shows the least bad one but tells the driver to consider delaying departure.

### Routing

- **Truck routing.** Valhalla's truck profile needs the gross vehicle weight, but the user enters the payload. I send an assumed empty truck weight (about 35,000 lb for a tractor and trailer) plus the load. The risk rules still use only the payload. If the total goes over 80,000 lb (the US federal limit) the app shows a soft warning.
- **Always 3 routes.** Valhalla often returns fewer than 3 (1 for Dallas to Oklahoma City, 2 for Chicago to Denver). OSRM fills the gap first (marked as a car route). If there are still fewer than 3, Valhalla is asked for a truck route through a point beside the middle of the main route, on the left and then the right. Routes sharing more than 85% of their road with one already picked are skipped, and so are detours longer than 1.5x the main route.
- **ETA inside a maneuver.** The routing engines give a length and time per maneuver (one stretch of road). Within a maneuver the time is spread by distance, so speed is assumed constant on that stretch.

### Heatmap

- **The slider is relative to departure**, from departure time to 48 hours after.
- **Area.** Points within about 20 miles of any of the three routes, on a fixed 0.25° grid, capped at about 400 points. A full bounding box would be thousands of points on a long trip, which is too many for Open-Meteo's free tier. The fixed grid also lets the cache reuse points between searches.
- **One request, then no network.** The backend fetches all 49 hours in one batched call and sends a compact array. Moving the slider only changes which hour the map draws, so it stays smooth.
- **The heatmap shows a smooth risk score** from 0 to 4 for the user's load. Its whole number part is always the official level (same rules as the checkpoints), and the fraction shows how close the worst condition is to the next level. For example 30 mph wind is 1.5: Moderate, halfway to High. With only the 5 levels a calm day would be one flat color, and the score shows where conditions are building.
- **The truck moves with the slider.** A marker shows where the truck on the selected route would be at that hour, so you can see whether it reaches a storm before or after it passes.

### Hosting

- **Place search is US only.** The routing and the risk rules are in US units, so the search boxes only suggest places in the lower 48 states.
- **Free Render instance.** It sleeps after 15 minutes without traffic and takes about a minute to wake. A scheduled ping keeps it awake most of the time, and the frontend shows a "waking up the server" screen explaining the wait when it is asleep.

## API

`GET /api/health` returns `{"status": "ok"}`. The frontend uses it to tell when the free server has woken up.

`GET /api/geocode?q=denver` returns up to 5 US places (`label`, `lat`, `lon`) for the search boxes.

`POST /api/heatmap` takes the same body as `/api/plan` and returns the grid points, the 49 times (departure to +48 h) and a score per point per hour (risk score x 10, so 0 to 40).

`POST /api/plan`

```json
{
  "origin": {"lat": 32.7767, "lon": -96.797},
  "destination": {"lat": 39.7392, "lon": -104.9903},
  "depart_at": "2026-10-11T14:00:00-05:00",
  "load_lb": 42000,
  "interval_mi": 25
}
```

`interval_mi` is optional (10, 25 or 50). The response has the recommended route, and for each route: its rank, the rule it lost on, distance, duration, miles at each risk level, average risk, the line split into colored pieces by risk, and every checkpoint with its ETA, weather, level and reason. Invalid input returns 400 with a message per field. If a routing or weather service fails, it returns 502.

## Running locally

Backend (needs [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
uv sync
uv run pytest
uv run python manage.py runserver
```

No API keys are needed. Tests run offline against real responses saved in `backend/planner/tests/fixtures`.

Frontend (needs Node 20+), in a second terminal:

```bash
cd frontend
npm install
cp .env.example .env   # points the app at http://localhost:8000
npm run dev
```

Then open http://localhost:5173.

## Deployment

**Backend on Render** (free web service, Oregon, root directory `backend`, redeploys only when `backend/` changes):

- Build: `pip install uv && uv sync --frozen --no-dev`
- Start: `.venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120`
- Health check: `/api/health`
- Environment: `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`, `CORS_ALLOWED_ORIGINS` (the Vercel URL), `PYTHON_VERSION=3.13.5`

One worker with threads, so every request shares the same in-memory cache (the heatmap reuses the routes the plan just fetched).

**Frontend on Vercel**, connected to this GitHub repo with root directory `frontend`, so every push to `main` that changes `frontend/` deploys to production. `VITE_API_URL` is set to the Render URL.

**Keep-alive.** `.github/workflows/keep-alive.yml` pings `/api/health` every 10 minutes (repository variable `BACKEND_URL`) so the free instance stays awake.
