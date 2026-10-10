from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .geo import haversine_mi
from .routes import SAMPLING_INTERVALS_MI

MAX_DAYS_AHEAD = 7
# a little slack so "now" from the browser isn't rejected by clock drift
PAST_GRACE = timedelta(minutes=15)


class PointSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


class PlanRequestSerializer(serializers.Serializer):
    origin = PointSerializer()
    destination = PointSerializer()
    depart_at = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=0, max_value=100_000)
    interval_mi = serializers.ChoiceField(
        choices=SAMPLING_INTERVALS_MI, required=False, allow_null=True
    )

    def validate_depart_at(self, value):
        now = timezone.now()
        if value < now - PAST_GRACE:
            raise serializers.ValidationError("Departure can't be in the past.")
        if value > now + timedelta(days=MAX_DAYS_AHEAD):
            raise serializers.ValidationError(
                f"Departure must be within {MAX_DAYS_AHEAD} days, the forecast doesn't go further."
            )
        return value

    def validate(self, attrs):
        origin = (attrs["origin"]["lat"], attrs["origin"]["lon"])
        destination = (attrs["destination"]["lat"], attrs["destination"]["lon"])
        if haversine_mi(origin, destination) < 1:
            raise serializers.ValidationError("Origin and destination are the same place.")
        return attrs
