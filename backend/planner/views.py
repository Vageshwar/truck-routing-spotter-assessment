from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import geocode
from .plan import plan_trip
from .serializers import PlanRequestSerializer
from .valhalla import RoutingError
from .weather import WeatherError


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


@api_view(["POST"])
def plan(request):
    serializer = PlanRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        result = plan_trip(
            origin=(data["origin"]["lat"], data["origin"]["lon"]),
            destination=(data["destination"]["lat"], data["destination"]["lon"]),
            depart_at=data["depart_at"],
            load_lb=data["load_lb"],
            interval_mi=data.get("interval_mi"),
        )
    except (RoutingError, WeatherError) as exc:
        # an outside service failed, not the client's request
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    return Response(result)


@api_view(["GET"])
def places(request):
    query = request.query_params.get("q", "")
    if len(query.strip()) < 3:
        return Response([])
    try:
        return Response(geocode.search(query))
    except geocode.GeocodeError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
