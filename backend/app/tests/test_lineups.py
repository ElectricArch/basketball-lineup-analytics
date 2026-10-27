import json
from itertools import combinations
from pathlib import Path
from uuid import UUID

from django.db import models
from django.test import TestCase, override_settings
from django.core.cache import cache
from app.demo_data import build_demo_data

from app.dbmodels.models import Game, Player, Possession, Team
from app.helpers.lineups import get_lineup_league_summary_stats


BACKEND_DIR = Path(__file__).resolve().parents[2]
EXPECTED_PATH = BACKEND_DIR / 'app/tests/fixtures/synthetic_expected.json'
PERFORMANCE_FIELDS = {
    'offensive_rating', 'defensive_rating', 'net_rating',
    'offensive_efg_pct', 'defensive_efg_pct',
    'offensive_rebound_pct', 'defensive_rebound_pct',
    'offensive_turnover_rate', 'opponent_turnover_rate',
}


@override_settings(LINEUP_THROTTLE_RATE="100000/min")
class LineupAggregationTests(TestCase):
    def setUp(self):
        cache.clear()

    @classmethod
    def setUpTestData(cls):
        cls.team_a = Team.objects.create(id=UUID(int=1), name='A')
        cls.team_b = Team.objects.create(id=UUID(int=2), name='B')
        cls.game = Game.objects.create(id=UUID(int=3), date='2025-10-22')
        cls.a = [UUID(int=100 + i) for i in range(6)]
        cls.b = [UUID(int=200 + i) for i in range(5)]
        Player.objects.bulk_create([
            Player(id=player_id, team=team, name=f'Player {player_id.int}')
            for team, player_ids in ((cls.team_a, cls.a), (cls.team_b, cls.b))
            for player_id in player_ids
        ])

    def add_possession(self, number, offense=None, defense=None, reverse=False, **stats):
        values = {
            field.name: 0 for field in Possession._meta.fields
            if isinstance(field, models.IntegerField)
        }
        values.update(period=1, seconds=10.0)
        values.update(stats)
        return Possession.objects.create(
            id=UUID(int=1000 + number), game=self.game,
            offensive_team=self.team_b if reverse else self.team_a,
            defensive_team=self.team_a if reverse else self.team_b,
            offensive_player_ids=offense if offense is not None else (self.b if reverse else self.a[:5]),
            defensive_player_ids=defense if defense is not None else (self.a[:5] if reverse else self.b),
            **values,
        )

    def team_a_records(self, size):
        return [r for r in get_lineup_league_summary_stats(size) if r['team_id'] == str(self.team_a.id)]

    def test_empty_database(self):
        self.assertEqual(get_lineup_league_summary_stats(), [])

    def test_all_smaller_combinations_are_generated(self):
        self.add_possession(1, points=2)
        for size in range(1, 5):
            with self.subTest(size=size):
                records = self.team_a_records(size)
                expected = set(combinations([str(p) for p in self.a[:5]], size))
                self.assertEqual({tuple(r['player_ids']) for r in records}, expected)
                self.assertEqual(len(records), len(expected))
                for record in records:
                    self.assertEqual(record['offensive_possessions'], 1)
                    self.assertEqual(record['offensive_points'], 2)

    def test_shared_subset_aggregates_across_different_five_player_units(self):
        self.add_possession(1, points=2)
        self.add_possession(2, offense=self.a[:4] + [self.a[5]], points=3)
        records = {tuple(r['player_ids']): r for r in self.team_a_records(3)}
        shared = records[tuple(str(p) for p in self.a[:3])]
        self.assertEqual(shared['offensive_possessions'], 2)
        self.assertEqual(shared['offensive_points'], 5)
        exclusive = records[tuple(str(p) for p in (self.a[0], self.a[1], self.a[4]))]
        self.assertEqual(exclusive['offensive_possessions'], 1)

    def test_sides_and_underlying_fields_are_not_swapped(self):
        self.add_possession(1, points=2, rebounds_offense=1, rebounds_defense=2, turnovers=1)
        self.add_possession(2, reverse=True, points=3, rebounds_offense=4, rebounds_defense=5, turnovers=2)
        self.add_possession(3, points=1)
        records = get_lineup_league_summary_stats(5)
        a, b = records
        self.assertEqual((a['offensive_possessions'], a['defensive_possessions']), (2, 1))
        self.assertEqual((b['offensive_possessions'], b['defensive_possessions']), (1, 2))
        self.assertEqual((a['offensive_points'], a['defensive_points']), (3, 3))
        self.assertEqual(a['offensive_rebounds_offense'], 1)
        self.assertEqual(a['offensive_rebounds_defense'], 2)
        self.assertEqual(a['defensive_rebounds_offense'], 4)
        self.assertEqual(a['defensive_rebounds_defense'], 5)
        self.assertEqual(a['defensive_turnovers'], 2)
        self.assertEqual(b['defensive_turnovers'], 1)

    def test_percentages_use_aggregated_makes_and_attempts_on_both_sides(self):
        for reverse in (False, True):
            offset = 2 if reverse else 0
            self.add_possession(1 + offset, reverse=reverse, fg_made=2, fg_attempted=2,
                                fg2_made=1, fg2_attempted=1, fg3_made=1, fg3_attempted=1)
            self.add_possession(2 + offset, reverse=reverse, fg_made=1, fg_attempted=6,
                                fg2_made=1, fg2_attempted=3, fg3_made=0, fg3_attempted=3)
        record = self.team_a_records(5)[0]
        for side in ('offensive', 'defensive'):
            self.assertEqual(record[f'{side}_fg_pct'], 3 / 8)
            self.assertEqual(record[f'{side}_fg2_pct'], 2 / 4)
            self.assertEqual(record[f'{side}_fg3_pct'], 1 / 4)

    def test_zero_attempts_and_unobserved_side_are_zero(self):
        self.add_possession(1)
        record = self.team_a_records(5)[0]
        self.assertEqual(record['defensive_possessions'], 0)
        self.assertEqual(record['defensive_points'], 0)
        for side in ('offensive', 'defensive'):
            for shot_type in ('fg', 'fg2', 'fg3'):
                self.assertEqual(record[f'{side}_{shot_type}_pct'], 0)

    def test_total_possessions_for_every_lineup_size(self):
        self.add_possession(1)
        self.add_possession(2, reverse=True)
        for size in range(1, 6):
            for record in get_lineup_league_summary_stats(size):
                self.assertEqual(record['total_possessions'],
                                 record['offensive_possessions'] + record['defensive_possessions'])
                self.assertEqual(record['total_possessions'], 2)

    def test_performance_metrics_use_aggregated_totals_without_rounding(self):
        self.add_possession(1, points=3, fg_made=1, fg3_made=1, fg_attempted=1,
                            rebounds_offense=1, rebound_opportunities=1)
        self.add_possession(2, points=2, fg_made=1, fg_attempted=4,
                            rebounds_offense=1, rebounds_defense=2, rebound_opportunities=3, turnovers=1)
        self.add_possession(3, turnovers=1)
        self.add_possession(4, reverse=True, points=2, fg_made=1, fg_attempted=2,
                            rebounds_offense=1, rebounds_defense=1, rebound_opportunities=2, turnovers=1)
        self.add_possession(5, reverse=True, points=3, fg_made=1, fg3_made=1, fg_attempted=1,
                            rebounds_defense=1, rebound_opportunities=1)
        expected = {
            'offensive_rating': 5 / 3 * 100,
            'defensive_rating': 5 / 2 * 100,
            'net_rating': 5 / 3 * 100 - 5 / 2 * 100,
            'offensive_efg_pct': 2.5 / 5,
            'defensive_efg_pct': 2.5 / 3,
            'offensive_rebound_pct': 2 / 4,
            'defensive_rebound_pct': 2 / 3,
            'offensive_turnover_rate': 2 / 3 * 100,
            'opponent_turnover_rate': 1 / 2 * 100,
        }
        for size in range(1, 6):
            for record in self.team_a_records(size):
                for field, value in expected.items():
                    with self.subTest(size=size, field=field):
                        self.assertEqual(record[field], value)

    def test_performance_metrics_return_zero_for_every_zero_denominator(self):
        self.add_possession(1)
        for record in get_lineup_league_summary_stats(5):
            for field in PERFORMANCE_FIELDS:
                with self.subTest(team=record['team_id'], field=field):
                    self.assertEqual(record[field], 0)

    def test_unobserved_side_is_zero_and_net_rating_preserves_sign(self):
        self.add_possession(1, points=3, fg_made=1, fg3_made=1, fg_attempted=1)
        a, b = get_lineup_league_summary_stats(5)
        self.assertEqual(a['offensive_rating'], 300)
        self.assertEqual(a['defensive_rating'], 0)
        self.assertEqual(a['net_rating'], 300)
        self.assertEqual(a['offensive_efg_pct'], 1.5)
        self.assertEqual(a['defensive_efg_pct'], 0)
        self.assertEqual(b['offensive_rating'], 0)
        self.assertEqual(b['defensive_rating'], 300)
        self.assertEqual(b['net_rating'], -300)
        self.assertEqual(b['offensive_efg_pct'], 0)
        self.assertEqual(b['defensive_efg_pct'], 1.5)

    def test_array_order_does_not_change_identity_or_player_order(self):
        self.add_possession(1, offense=list(reversed(self.a[:5])), defense=list(reversed(self.b)))
        self.add_possession(2)
        records = get_lineup_league_summary_stats(3)
        keys = [(r['team_id'], tuple(r['player_ids'])) for r in records]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(keys), 20)
        for record in records:
            self.assertEqual(record['player_ids'], sorted(record['player_ids']))
            self.assertEqual(record['players'], [
                {'player_id': p, 'name': f'Player {UUID(p).int}'} for p in record['player_ids']
            ])
            self.assertEqual(record['offensive_possessions'] + record['defensive_possessions'], 2)

    def test_lineup_size_normalization(self):
        self.add_possession(1)
        for value, expected in ((None, 5), ('invalid', 5), (0, 1), (-2, 1), (6, 5), ('3', 3)):
            with self.subTest(value=value):
                self.assertEqual(get_lineup_league_summary_stats(value), get_lineup_league_summary_stats(expected))

    def test_query_count_is_constant(self):
        self.add_possession(1)
        self.add_possession(2, offense=self.a[:4] + [self.a[5]])
        with self.assertNumQueries(3):
            get_lineup_league_summary_stats(3)

    def test_endpoint_keeps_existing_query_parameter_behavior(self):
        self.add_possession(1)
        for query, size in (('', 5), ('?lineup_size=3', 3), ('?lineup_size=0', 1),
                            ('?lineup_size=bad', 5), ('?lineup_size=9', 5)):
            with self.subTest(query=query):
                response = self.client.get('/api/v1/lineups' + query)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), get_lineup_league_summary_stats(size))


@override_settings(LINEUP_THROTTLE_RATE="100000/min")
class LineupQueryTests(TestCase):
    def setUp(self):
        cache.clear()

    @classmethod
    def setUpTestData(cls):
        cls.team_a = Team.objects.create(id=UUID(int=1), name='Team A')
        cls.team_b = Team.objects.create(id=UUID(int=2), name='Team B')
        cls.a = [UUID(int=100 + i) for i in range(6)]
        cls.b = [UUID(int=200 + i) for i in range(5)]
        Player.objects.bulk_create([
            Player(id=p, team=team, name=f'Player {p.int}')
            for team, players in ((cls.team_a, cls.a), (cls.team_b, cls.b))
            for p in players
        ])
        game = Game.objects.create(id=UUID(int=3), date='2025-10-22')
        rows = (
            (cls.a[:5], False, dict(points=3, fg_made=1, fg3_made=1, fg_attempted=1,
                                   rebounds_offense=1, rebound_opportunities=1)),
            (cls.a[:5], False, dict(fg_attempted=2, rebounds_defense=2,
                                   rebound_opportunities=2, turnovers=1)),
            (cls.a[:4] + [cls.a[5]], False, dict(points=2, fg_made=1, fg_attempted=1)),
            (cls.a[:5], True, dict(points=1, fg_attempted=1, rebounds_offense=1,
                                  rebounds_defense=1, rebound_opportunities=2, turnovers=1)),
        )
        for number, (players, reverse, stats) in enumerate(rows):
            values = {f.name: 0 for f in Possession._meta.fields if isinstance(f, models.IntegerField)}
            values.update(period=1, seconds=10.0)
            values.update(stats)
            Possession.objects.create(
                id=UUID(int=1000 + number), game=game,
                offensive_team=cls.team_b if reverse else cls.team_a,
                defensive_team=cls.team_a if reverse else cls.team_b,
                offensive_player_ids=cls.b if reverse else players,
                defensive_player_ids=players if reverse else cls.b,
                **values,
            )

    def fetch(self, **params):
        response = self.client.get('/api/v1/lineups', params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_team_names_and_default_order(self):
        records = self.fetch()
        self.assertEqual([r['team_name'] for r in records], ['Team B', 'Team A', 'Team A'])
        self.assertEqual([r['total_possessions'] for r in records], [4, 3, 1])
        self.assertEqual(records, self.fetch(lineup_size=5))

    def test_team_filter_preserves_full_lineup_statistics(self):
        expected = [r for r in self.fetch() if r['team_id'] == str(self.team_a.id)]
        self.assertEqual(len(expected), 2)
        self.assertEqual(self.fetch(team_id=str(self.team_a.id)), expected)

    def test_unknown_team_returns_empty(self):
        self.assertEqual(self.fetch(team_id=str(UUID(int=9999))), [])

    def test_malformed_team_returns_empty(self):
        for value in ('invalid', '', '123', "' OR 1=1"):
            with self.subTest(value=value):
                self.assertEqual(self.fetch(team_id=value), [])

    def test_player_filter_preserves_full_lineup_statistics(self):
        for size in (1, 3, 5):
            for player in (self.a[0], self.a[4], self.b[0]):
                with self.subTest(size=size, player=player):
                    expected = [r for r in self.fetch(lineup_size=size) if str(player) in r['player_ids']]
                    self.assertTrue(expected)
                    self.assertEqual(self.fetch(lineup_size=size, player_id=str(player)), expected)

    def test_unknown_player_returns_empty(self):
        self.assertEqual(self.fetch(player_id=str(UUID(int=9999))), [])

    def test_malformed_player_returns_empty(self):
        for value in ('invalid', '', '123'):
            with self.subTest(value=value):
                self.assertEqual(self.fetch(player_id=value), [])

    def test_combined_team_and_player_filters(self):
        expected = self.fetch(player_id=str(self.a[0]))
        self.assertEqual(self.fetch(team_id=str(self.team_a.id), player_id=str(self.a[0])), expected)
        self.assertEqual(self.fetch(team_id=str(self.team_b.id), player_id=str(self.a[0])), [])

    def test_uuid_strings_are_canonicalized(self):
        player = Player.objects.create(id=UUID('abcdefab-cdef-abcd-efab-cdefabcdefab'),
                                       team=self.team_a, name='Alternate')
        possession = Possession.objects.order_by('id').first()
        possession.offensive_player_ids = self.a[:4] + [player.id]
        possession.save(update_fields=['offensive_player_ids'])
        expected = self.fetch(player_id=str(player.id))
        self.assertTrue(expected)
        self.assertEqual(self.fetch(player_id=str(player.id).upper()), expected)
        self.assertEqual(self.fetch(team_id=self.team_a.id.hex), self.fetch(team_id=str(self.team_a.id)))

    def test_min_possessions_is_inclusive_and_uses_total(self):
        records = self.fetch(min_possessions=3)
        self.assertEqual([r['total_possessions'] for r in records], [4, 3])
        self.assertEqual(records[1]['offensive_possessions'], 2)
        self.assertEqual(records[1]['defensive_possessions'], 1)
        self.assertEqual(self.fetch(min_possessions=5), [])

    def test_invalid_min_possessions_means_zero(self):
        expected = self.fetch()
        for value in ('invalid', '', '-1', '2.5', '0'):
            with self.subTest(value=value):
                self.assertEqual(self.fetch(min_possessions=value), expected)

    def test_every_supported_sort_field_in_both_directions(self):
        fields = PERFORMANCE_FIELDS | {'total_possessions', 'offensive_possessions', 'defensive_possessions'}
        baseline = self.fetch()
        for field in fields:
            for order in ('asc', 'desc'):
                with self.subTest(field=field, order=order):
                    expected = sorted(baseline, key=lambda r: (
                        r[field] if order == 'asc' else -r[field], r['team_id'], r['player_ids'],
                    ))
                    self.assertEqual(self.fetch(sort_by=field, sort_order=order), expected)

    def test_unsupported_sort_field_falls_back_to_total_possessions(self):
        for field in ('unknown', 'team_name', 'offensive_points', '__class__', ''):
            for order in ('asc', 'desc'):
                with self.subTest(field=field, order=order):
                    self.assertEqual(self.fetch(sort_by=field, sort_order=order),
                                     self.fetch(sort_by='total_possessions', sort_order=order))

    def test_unsupported_sort_order_falls_back_to_descending(self):
        for order in ('invalid', 'ASC', ''):
            with self.subTest(order=order):
                self.assertEqual(self.fetch(sort_by='net_rating', sort_order=order),
                                 self.fetch(sort_by='net_rating', sort_order='desc'))

    def test_ties_use_ascending_team_and_player_ids_in_both_directions(self):
        for order in ('asc', 'desc'):
            records = self.fetch(lineup_size=1, sort_order=order)
            tied = [r for r in records if r['total_possessions'] == 4]
            self.assertEqual(len(tied), 9)
            keys = [(r['team_id'], r['player_ids']) for r in tied]
            self.assertEqual(keys, sorted(keys))
            self.assertEqual(records, self.fetch(lineup_size=1, sort_order=order))

    def test_limit_is_applied_after_all_filters_and_sorting(self):
        params = dict(team_id=str(self.team_a.id), player_id=str(self.a[0]), min_possessions=1,
                      sort_by='net_rating', sort_order='desc')
        expected = self.fetch(**params)
        self.assertEqual(len(expected), 2)
        self.assertEqual(expected[0]['total_possessions'], 1)
        self.assertEqual(self.fetch(**params, limit=1), expected[:1])
        self.assertEqual(self.fetch(**params, limit=100), expected)
        params['min_possessions'] = 3
        self.assertEqual(self.fetch(**params, limit=1), expected[1:])

    def test_invalid_limit_uses_bounded_default(self):
        expected = self.fetch()
        for value in ('invalid', '', '0', '-1', '1.5'):
            with self.subTest(value=value):
                self.assertEqual(self.fetch(limit=value), expected)

    def test_helper_enforces_sort_whitelist(self):
        self.assertEqual(get_lineup_league_summary_stats(sort_by='players', sort_order='invalid'),
                         get_lineup_league_summary_stats())


class SyntheticLineupRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        data = build_demo_data()
        Team.objects.bulk_create([Team(**row) for row in data['teams']])
        Game.objects.bulk_create([Game(**row) for row in data['games']])
        Player.objects.bulk_create([Player(**row) for row in data['players']])
        Possession.objects.bulk_create([Possession(**row) for row in data['possessions']])

    def test_independent_lineups_match_every_field(self):
        actual = {(r['team_id'], tuple(r['player_ids'])): r
                  for r in get_lineup_league_summary_stats(5)}
        for expected in json.loads(EXPECTED_PATH.read_text(encoding='utf-8')):
            key = (expected['team_id'], tuple(expected['player_ids']))
            with self.subTest(lineup=key):
                self.assertIn(key, actual)
                self.assertEqual(actual[key], expected)
