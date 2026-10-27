"""Stdlib-only checks; no Django import or database access."""
from copy import deepcopy
from itertools import combinations
import json
from pathlib import Path
import secrets
import unittest

from app.configuration import load_environment
from app.demo_data import COUNTING_FIELDS, build_demo_data, validate_demo_data
from app.safety import bounded_http_limit, validate_five_players, validate_query


class ConfigurationTests(unittest.TestCase):
    def environment(self, **changes):
        env = {
            "APP_ENV": "test", "DJANGO_SECRET_KEY": secrets.token_urlsafe(48),
            "DATABASE_URL": "postgresql://lineup_migrator@127.0.0.1:55432/lineup_demo_test",
        }
        env.update(changes)
        return env

    def test_required_values_have_no_fallback(self):
        for name in ("APP_ENV", "DJANGO_SECRET_KEY", "DATABASE_URL"):
            env = self.environment()
            del env[name]
            with self.subTest(variable=name), self.assertRaises(ValueError):
                load_environment(env)

    def test_local_defaults_are_restricted(self):
        cfg = load_environment(self.environment())
        self.assertFalse(cfg["debug"])
        self.assertFalse(cfg["trust_proxy"])
        self.assertEqual(cfg["database_host"], "127.0.0.1")
        self.assertEqual(cfg["statement_timeout"], 5000)
        self.assertNotIn("*", cfg["hosts"])
        self.assertIn("http://127.0.0.1:4210", cfg["origins"])

    def test_placeholder_and_low_entropy_secrets_are_refused(self):
        for value in ("", "short", "x" * 80, "replace-" + "abcd012345" * 8):
            with self.subTest(case=len(value)), self.assertRaises(ValueError):
                load_environment(self.environment(DJANGO_SECRET_KEY=value))

    def test_local_database_indirection_and_remote_targets_are_refused(self):
        base = "postgresql://lineup_migrator@127.0.0.1/lineup_demo_test"
        values = ["sqlite:///local.db", "postgresql://db.invalid/lineup_demo_test",
                  "postgresql://127.0.0.1/valuable", base + "?host=db.invalid",
                  base + "?service=other", base + "?options=anything",
                  base + "?sslmode=disable&sslmode=require", base + "#ignored"]
        for index, value in enumerate(values):
            with self.subTest(case=index), self.assertRaises(ValueError):
                load_environment(self.environment(DATABASE_URL=value))

    def test_production_requires_hosts_tls_and_verified_proxy_boundary(self):
        env = self.environment(APP_ENV="production", DJANGO_ALLOWED_HOSTS="api.example.invalid",
            DATABASE_URL="postgresql://lineup_reader@db.example.invalid/lineup_demo?sslmode=verify-full&sslrootcert=/trusted/ca.crt",
            CORS_ALLOWED_ORIGINS="https://ui.example.invalid")
        self.assertFalse(load_environment(env)["debug"])
        for changes in ({"DJANGO_ALLOWED_HOSTS": ""}, {"DJANGO_ALLOWED_HOSTS": "*"},
                        {"DJANGO_DEBUG": "true"}, {"CORS_ALLOWED_ORIGINS": "http://ui.example.invalid"},
                        {"DATABASE_URL": "postgresql://db.example.invalid/lineup_demo?sslmode=require"},
                        {"DJANGO_TRUST_PROXY": "true"}):
            with self.subTest(names=list(changes)), self.assertRaises(ValueError):
                load_environment(dict(env, **changes))
        env.update(DJANGO_TRUST_PROXY="true", DJANGO_PROXY_CONFIRMATION="headers-stripped")
        self.assertTrue(load_environment(env)["trust_proxy"])

    def test_origin_and_resource_values_are_validated(self):
        for changes in ({"CORS_ALLOWED_ORIGINS": "https://user:pass@example.invalid"},
                        {"CORS_ALLOWED_ORIGINS": "https://example.invalid/path"},
                        {"DB_CONNECT_TIMEOUT": "0"}, {"DB_STATEMENT_TIMEOUT_MS": "30001"},
                        {"DB_CONN_MAX_AGE": "-1"}, {"DJANGO_DEBUG": "maybe"}):
            with self.subTest(names=list(changes)), self.assertRaises(ValueError):
                load_environment(self.environment(**changes))


class RequestBoundsTests(unittest.TestCase):
    def test_missing_invalid_and_oversized_limits(self):
        for value in (None, "", "invalid", "1.5", "0", "-1", "101", "1000000000"):
            with self.subTest(value=value):
                self.assertEqual(bounded_http_limit(value), 100)
        for value in ("1", "10", "25", "50", "100"):
            self.assertEqual(bounded_http_limit(value), int(value))

    def test_query_size_pair_count_and_numeric_width(self):
        validate_query("limit=25", [("limit", "25")])
        for raw, pairs in (("x" * 2049, []), ("", [("x", "y")] * 17),
                           ("", [("limit", "9" * 25)]), ("", [("team_id", "x" * 65)])):
            with self.assertRaises(ValueError):
                validate_query(raw, pairs)

    def test_five_distinct_same_team_players_are_required(self):
        roster = {str(i): "team" for i in range(6)}
        validate_five_players(list(roster)[:5], "team", roster)
        for values in (["0"] * 5, list(roster), ["0", "1", "2", "3", "unknown"], "01234"):
            with self.assertRaises(ValueError):
                validate_five_players(values, "team", roster)
        with self.assertRaises(ValueError):
            validate_five_players(list(roster)[:5], "other", roster)


class SyntheticFixtureTests(unittest.TestCase):
    def setUp(self):
        self.data = build_demo_data()

    def test_deterministic_size_and_validation(self):
        self.assertEqual(self.data, build_demo_data())
        self.assertEqual({k: len(v) for k, v in self.data.items()},
                         {"teams": 3, "players": 21, "games": 3, "possessions": 36})
        validate_demo_data(self.data)

    def test_all_sizes_overlap_catalog_and_default_results(self):
        units = {}
        for size in range(1, 6):
            visits = {}
            for row in self.data["possessions"]:
                for side in ("offensive", "defensive"):
                    team = row[side + "_team_id"]
                    for lineup in combinations(sorted(row[side + "_player_ids"]), size):
                        key = (team, lineup)
                        visits[key] = visits.get(key, 0) + 1
            units[size] = visits
            self.assertTrue(visits)
        self.assertEqual(len(units[1]), 21)
        self.assertEqual(set(player for _, lineup in units[1] for player in lineup),
                         {p["id"] for p in self.data["players"]})
        self.assertEqual(sorted(units[5].values()), [2, 2, 2, 6, 6, 6, 16, 16, 16])
        self.assertEqual(sum(n >= 10 for n in units[5].values()), 3)
        self.assertGreater(max(units[3].values()), 16)

    def test_independent_golden_counts_match_fixture_events(self):
        expected_path = Path(__file__).parent / "fixtures/synthetic_expected.json"
        expected_rows = json.loads(expected_path.read_text())
        for expected in expected_rows:
            for side in ("offensive", "defensive"):
                rows = [r for r in self.data["possessions"]
                        if r[side + "_team_id"] == expected["team_id"] and
                        sorted(r[side + "_player_ids"]) == expected["player_ids"]]
                self.assertEqual(len(rows), expected[side + "_possessions"])
                for field in COUNTING_FIELDS:
                    with self.subTest(side=side, field=field):
                        self.assertEqual(sum(r[field] for r in rows), expected[side + "_" + field])
        self.assertEqual(expected_rows[1]["defensive_possessions"], 0)
        self.assertEqual(expected_rows[1]["offensive_fg_attempted"], 0)

    def test_invalid_fixture_is_rejected_before_any_database_access(self):
        for change in ("duplicate", "foreign_player", "negative", "shooting", "nonfinite"):
            data = deepcopy(self.data)
            row = data["possessions"][0]
            if change == "duplicate":
                row["offensive_player_ids"][1] = row["offensive_player_ids"][0]
            elif change == "foreign_player":
                row["offensive_player_ids"][0] = row["defensive_player_ids"][0]
            elif change == "negative":
                row["turnovers"] = -1
            elif change == "shooting":
                row["points"] = 99
            else:
                row["seconds"] = float("nan")
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_demo_data(data)


if __name__ == "__main__":
    unittest.main()
