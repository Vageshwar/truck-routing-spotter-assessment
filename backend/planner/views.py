from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import geocode
from .heatmap import heatmap_for_trip
from .plan import plan_trip
from .serializers import PlanRequestSerializer
from .valhalla import RoutingError
from .weather import WeatherError


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


def _trip_args(request) -> dict:
    serializer = PlanRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    return {
        "origin": (data["origin"]["lat"], data["origin"]["lon"]),
        "destination": (data["destination"]["lat"], data["destination"]["lon"]),
        "depart_at": data["depart_at"],
        "load_lb": data["load_lb"],
        "interval_mi": data.get("interval_mi"),
    }


def _service_error(exc: Exception) -> Response:
    # an outside service failed, not the client's request
    return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


@api_view(["POST"])
def plan(request):
    args = _trip_args(request)
    try:
        return Response(plan_trip(**args))
    except (RoutingError, WeatherError) as exc:
        return _service_error(exc)


@api_view(["POST"])
def heatmap(request):
    """Takes the same body as /api/plan (the spacing is ignored)."""
    args = _trip_args(request)
    args.pop("interval_mi")
    try:
        return Response(heatmap_for_trip(**args))
    except (RoutingError, WeatherError) as exc:
        return _service_error(exc)


@api_view(["GET"])
def places(request):
    query = request.query_params.get("q", "")
    if len(query.strip()) < 3:
        return Response([])
    try:
        return Response(geocode.search(query))
    except geocode.GeocodeError as exc:
        return _service_error(exc)
