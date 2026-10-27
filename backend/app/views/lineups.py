"""Read-only lineup endpoint with separate response and dataset bounds."""
import logging
from threading import BoundedSemaphore
from uuid import UUID

from django.conf import settings
from django.db import DatabaseError
from rest_framework.exceptions import ParseError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from app.dbmodels.models import Player, Possession, Team
from app.helpers.lineups import SORT_FIELDS, get_lineup_league_summary_stats
from app.safety import (
    MAX_PLAYERS, MAX_POSSESSIONS, MAX_TEAMS, bounded_http_limit,
    validate_five_players, validate_query,
)

LOGGER = logging.getLogger(__name__)
WORK_SLOT = BoundedSemaphore(1)

class LineupThrottle(AnonRateThrottle):
    scope = "lineups"

    def get_rate(self):
        return settings.LINEUP_THROTTLE_RATE

    def get_ident(self, request):
        # Forwarded headers are not a trusted client identity.
        return request.META.get("REMOTE_ADDR", "")

def _parse_int_query_param(request, key, default, minimum=None, maximum=None):
    try:
        value = int(request.query_params.get(key, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value

def _parse_uuid_query_param(request, key):
    value = request.query_params.get(key)
    if value is None:
        return None
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        return ""

def _get_lineup_query_options(request):
    sort_by = request.query_params.get("sort_by", "total_possessions")
    sort_order = request.query_params.get("sort_order", "desc")
    return {
        "lineup_size": _parse_int_query_param(request, "lineup_size", 5, 1, 5),
        "team_id": _parse_uuid_query_param(request, "team_id"),
        "player_id": _parse_uuid_query_param(request, "player_id"),
        "min_possessions": _parse_int_query_param(request, "min_possessions", 0, minimum=0),
        "sort_by": sort_by if sort_by in SORT_FIELDS else "total_possessions",
        "sort_order": sort_order if sort_order in ("asc", "desc") else "desc",
        "limit": bounded_http_limit(request.query_params.get("limit")),
    }

def _dataset_is_supported():
    if (Possession.objects.count() > MAX_POSSESSIONS or
        Player.objects.count() > MAX_PLAYERS or Team.objects.count() > MAX_TEAMS):
        return False
    players = {str(pk): str(team) for pk, team in Player.objects.values_list("id", "team_id")}
    # Declaring an ArrayField size alone does not enforce distinct five-player arrays.
    for offense, defense, offensive_team, defensive_team in Possession.objects.values_list(
        "offensive_player_ids", "defensive_player_ids", "offensive_team_id", "defensive_team_id"
    ).iterator(chunk_size=200):
        try:
            validate_five_players(offense, offensive_team, players)
            validate_five_players(defense, defensive_team, players)
        except ValueError:
            return False
    return True

def _unavailable():
    return Response({"detail": "The lineup service is temporarily unavailable."},
                    status=503, headers={"Retry-After": "1"})

class LineupsLeagueSummary(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LineupThrottle]
    http_method_names = ["get", "head", "options"]

    def initial(self, request, *args, **kwargs):
        raw = request.META.get("QUERY_STRING", "")
        if len(raw) > 2048:
            raise ParseError("Request query is too large")
        pairs = [(key, value) for key in request.query_params for value in request.query_params.getlist(key)]
        try:
            validate_query(raw, pairs)
        except ValueError:
            raise ParseError("Request parameters are too large") from None
        super().initial(request, *args, **kwargs)

    def get(self, request):
        if not WORK_SLOT.acquire(blocking=False):
            return _unavailable()
        try:
            if not _dataset_is_supported():
                return _unavailable()
            return Response(get_lineup_league_summary_stats(**_get_lineup_query_options(request)))
        except (DatabaseError, KeyError, ValueError):
            LOGGER.warning("Lineup dataset unavailable or unsupported")
            return _unavailable()
        finally:
            WORK_SLOT.release()
