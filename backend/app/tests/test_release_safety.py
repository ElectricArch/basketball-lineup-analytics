"""Integration checks requiring pinned dependencies and a disposable PostgreSQL DB."""
from copy import deepcopy
from io import StringIO
from itertools import combinations
from unittest.mock import patch
from uuid import UUID

from django.core.cache import cache
from django.core.management import call_command, CommandError
from django.db import connection, DatabaseError, IntegrityError
from django.test import TestCase, override_settings

from app.dbmodels.models import Game, Player, Possession, Team
from app.demo_data import build_demo_data, identity
from app.helpers.lineups import get_lineup_league_summary_stats
from app.views.lineups import WORK_SLOT


def insert(data):
    for name, model in (("teams", Team), ("games", Game), ("players", Player), ("possessions", Possession)):
        model.objects.bulk_create([model(**row) for row in data[name]])


@override_settings(LINEUP_THROTTLE_RATE="100000/min")
class ApiSafetyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        data = build_demo_data()
        template = data["possessions"][0]
        data["possessions"] = []
        for index, team in enumerate(data["teams"]):
            roster = [p["id"] for p in data["players"] if p["team_id"] == team["id"]]
            other = data["teams"][(index + 1) % 3]
            defense = [p["id"] for p in data["players"] if p["team_id"] == other["id"]][:5]
            for unit in combinations(roster, 5):
                row = deepcopy(template)
                row.update(id=identity("safety/" + str(len(data["possessions"]))),
                    offensive_team_id=team["id"], defensive_team_id=other["id"],
                    offensive_player_ids=list(unit), defensive_player_ids=defense)
                data["possessions"].append(row)
        insert(data)

    def setUp(self):
        cache.clear()

    def test_http_cap_preserves_sorted_prefix_and_helper_is_unbounded(self):
        all_rows = get_lineup_league_summary_stats(3)
        self.assertEqual(len(all_rows), 105)
        for value in (None, "invalid", "0", "-1", "101", "999999", "1.5"):
            query = {"lineup_size": 3}
            if value is not None:
                query["limit"] = value
            response = self.client.get("/api/v1/lineups", query)
            with self.subTest(limit=value):
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), all_rows[:100])
        self.assertEqual(self.client.get("/api/v1/lineups", {"lineup_size": 3, "limit": 25}).json(), all_rows[:25])

    @override_settings(LINEUP_THROTTLE_RATE="2/min")
    def test_isolated_cache_throttles_and_ignores_forwarded_identity(self):
        with patch("app.views.lineups.get_lineup_league_summary_stats", return_value=[]):
            for forwarded in ("192.0.2.1", "192.0.2.2"):
                self.assertEqual(self.client.get("/api/v1/lineups", HTTP_X_FORWARDED_FOR=forwarded).status_code, 200)
            response = self.client.get("/api/v1/lineups", HTTP_X_FORWARDED_FOR="192.0.2.3")
            self.assertEqual(response.status_code, 429)
            self.assertIn("Retry-After", response)

    def test_oversized_query_is_rejected_before_aggregation(self):
        with patch("app.views.lineups.get_lineup_league_summary_stats") as helper:
            self.assertEqual(self.client.get("/api/v1/lineups", {"limit": "9" * 25}).status_code, 400)
            self.assertEqual(self.client.get("/api/v1/lineups?" + "x" * 2049).status_code, 400)
            helper.assert_not_called()

    def test_cardinality_guard_refuses_before_aggregation(self):
        with patch("app.views.lineups.MAX_POSSESSIONS", 0), patch("app.views.lineups.get_lineup_league_summary_stats") as helper:
            self.assertEqual(self.client.get("/api/v1/lineups").status_code, 503)
            helper.assert_not_called()

    def test_oversized_player_array_is_refused(self):
        row = Possession.objects.first()
        roster = list(Player.objects.filter(team_id=row.offensive_team_id).values_list("id", flat=True))
        Possession.objects.filter(id=row.id).update(offensive_player_ids=roster[:6])
        self.assertEqual(self.client.get("/api/v1/lineups").status_code, 503)

    def test_busy_process_refuses_without_waiting(self):
        self.assertTrue(WORK_SLOT.acquire(blocking=False))
        try:
            response = self.client.get("/api/v1/lineups")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response["Retry-After"], "1")
        finally:
            WORK_SLOT.release()

    def test_database_and_unexpected_errors_have_generic_json(self):
        for exception, status in ((DatabaseError("private diagnostic marker"), 503),
                                  (RuntimeError("private diagnostic marker"), 500)):
            with patch("app.views.lineups.get_lineup_league_summary_stats", side_effect=exception):
                response = self.client.get("/api/v1/lineups")
            self.assertEqual(response.status_code, status)
            self.assertNotIn("private diagnostic marker", response.content.decode())
            self.assertEqual(set(response.json()), {"detail"})

    def test_mutating_methods_are_unavailable(self):
        counts = (Team.objects.count(), Player.objects.count(), Possession.objects.count())
        for method in (self.client.post, self.client.put, self.client.patch, self.client.delete):
            self.assertEqual(method("/api/v1/lineups").status_code, 405)
        self.assertEqual(counts, (Team.objects.count(), Player.objects.count(), Possession.objects.count()))

    def test_synthetic_catalog_fits_bounded_response(self):
        response = self.client.get("/api/v1/lineups", {"lineup_size": 1, "limit": 100})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 21)


class DemoLoaderSafetyTests(TestCase):
    def run_loader(self):
        with override_settings(APP_ENV="test", DEMO_DATABASE_CONFIRMED=connection.settings_dict["NAME"]):
            call_command("load_demo_data", stdout=StringIO())

    def test_exact_fixture_idempotence(self):
        self.run_loader()
        before = list(Possession.objects.order_by("id").values())
        self.run_loader()
        self.assertEqual(before, list(Possession.objects.order_by("id").values()))
        self.assertEqual((Team.objects.count(), Player.objects.count(), Game.objects.count(), Possession.objects.count()), (3, 21, 3, 36))

    def test_conflicting_data_is_preserved(self):
        team = Team.objects.create(id=identity("conflicting-team"), name="Independent local record")
        with self.assertRaises(CommandError):
            self.run_loader()
        self.assertEqual(list(Team.objects.values_list("id", "name")), [(UUID(team.id), team.name)])
        self.assertFalse(Possession.objects.exists())

    def test_failed_insert_rolls_back_all_fixture_groups(self):
        with patch.object(Possession.objects, "bulk_create", side_effect=IntegrityError("test rollback")):
            with self.assertRaises(CommandError):
                self.run_loader()
        for model in (Team, Player, Game, Possession):
            self.assertFalse(model.objects.exists())

    def test_invalid_fixture_refuses_before_writes(self):
        data = build_demo_data()
        data["possessions"][0]["points"] = -1
        with patch("app.management.commands.load_demo_data.build_demo_data", return_value=data):
            with self.assertRaises(CommandError):
                self.run_loader()
        self.assertFalse(Team.objects.exists())

    def test_production_and_missing_confirmation_refuse(self):
        for changes in ({"APP_ENV": "production", "DEMO_DATABASE_CONFIRMED": connection.settings_dict["NAME"]},
                        {"APP_ENV": "test", "DEMO_DATABASE_CONFIRMED": ""}):
            with override_settings(**changes), self.assertRaises(CommandError):
                call_command("load_demo_data", stdout=StringIO())
        self.assertFalse(Team.objects.exists())
