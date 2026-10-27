from __future__ import annotations

"""Helpers for the lineup summary API."""

from itertools import combinations
from typing import Any

from app.dbmodels.models import Player, Possession, Team

COUNTING_FIELDS = (
    'points', 'shot_attempts', 'fg2_made', 'fg2_attempted',
    'fg3_made', 'fg3_attempted', 'fg_made', 'fg_attempted',
    'ft_made', 'ft_attempted', 'rebounds_offense', 'rebounds_defense',
    'rebound_opportunities', 'assists', 'steals', 'turnovers', 'blocks',
    'offensive_fouls', 'defensive_fouls', 'shooting_fouls',
    'shot_attempt_points', 'ft_potential_points', 'transition_take_fouls',
)
SIDES = ('offensive', 'defensive')
SORT_FIELDS = frozenset({
    'total_possessions', 'offensive_possessions', 'defensive_possessions',
    'offensive_rating', 'defensive_rating', 'net_rating',
    'offensive_efg_pct', 'defensive_efg_pct',
    'offensive_rebound_pct', 'defensive_rebound_pct',
    'offensive_turnover_rate', 'opponent_turnover_rate',
})
LineupRecord = dict[str, Any]


def _normalize_lineup_size(lineup_size: Any) -> int:
    try:
        normalized_lineup_size = int(lineup_size)
    except (TypeError, ValueError):
        return 5

    return max(1, min(5, normalized_lineup_size))


def get_lineup_league_summary_stats(
    lineup_size: int = 5,
    *,
    team_id: str | None = None,
    player_id: str | None = None,
    min_possessions: int = 0,
    sort_by: str = 'total_possessions',
    sort_order: str = 'desc',
    limit: int | None = None,
) -> list[LineupRecord]:
    """Aggregate every n-player unit, preserving each possession's field meanings."""
    lineup_size = _normalize_lineup_size(lineup_size)
    team_filter = team_id
    player_filter = player_id
    sort_by = sort_by if sort_by in SORT_FIELDS else 'total_possessions'
    sort_order = sort_order if sort_order in ('asc', 'desc') else 'desc'
    team_names = {str(team_id): name for team_id, name in Team.objects.values_list('id', 'name')}
    player_names = {str(player_id): name for player_id, name in Player.objects.values_list('id', 'name')}
    if team_filter is not None and team_filter not in team_names:
        return []
    if player_filter is not None and player_filter not in player_names:
        return []
    lineups: dict[tuple[str, tuple[str, ...]], LineupRecord] = {}
    possessions = Possession.objects.values(
        'offensive_team_id', 'defensive_team_id',
        'offensive_player_ids', 'defensive_player_ids', *COUNTING_FIELDS,
    )

    for possession in possessions.iterator():
        for side in SIDES:
            team_id = str(possession[f'{side}_team_id'])
            ordered_ids = sorted(str(player_id) for player_id in possession[f'{side}_player_ids'])
            for player_ids in combinations(ordered_ids, lineup_size):
                key = (team_id, player_ids)
                if key not in lineups:
                    lineups[key] = {
                        f'{prefix}_{field}': 0
                        for prefix in SIDES
                        for field in ('possessions', *COUNTING_FIELDS)
                    }
                record = lineups[key]
                record[f'{side}_possessions'] += 1
                for field in COUNTING_FIELDS:
                    record[f'{side}_{field}'] += possession[field]

    results = []
    for (team_id, player_ids), record in sorted(lineups.items()):
        record['total_possessions'] = record['offensive_possessions'] + record['defensive_possessions']
        if team_filter is not None and team_id != team_filter:
            continue
        if player_filter is not None and player_filter not in player_ids:
            continue
        if record['total_possessions'] < min_possessions:
            continue
        for side in SIDES:
            for shot_type in ('fg', 'fg2', 'fg3'):
                attempted = record[f'{side}_{shot_type}_attempted']
                record[f'{side}_{shot_type}_pct'] = (
                    record[f'{side}_{shot_type}_made'] / attempted if attempted else 0
                )
            possession_count = record[f'{side}_possessions']
            record[f'{side}_rating'] = (
                record[f'{side}_points'] / possession_count * 100 if possession_count else 0
            )
            attempted = record[f'{side}_fg_attempted']
            record[f'{side}_efg_pct'] = (
                (record[f'{side}_fg_made'] + 0.5 * record[f'{side}_fg3_made']) / attempted
                if attempted else 0
            )
        record['net_rating'] = record['offensive_rating'] - record['defensive_rating']
        for side, rebound_side, turnover_label in (
            ('offensive', 'offense', 'offensive'),
            ('defensive', 'defense', 'opponent'),
        ):
            opportunities = record[f'{side}_rebound_opportunities']
            record[f'{side}_rebound_pct'] = (
                record[f'{side}_rebounds_{rebound_side}'] / opportunities if opportunities else 0
            )
            possession_count = record[f'{side}_possessions']
            record[f'{turnover_label}_turnover_rate'] = (
                record[f'{side}_turnovers'] / possession_count * 100 if possession_count else 0
            )
        record['team_id'] = team_id
        record['team_name'] = team_names[team_id]
        record['player_ids'] = list(player_ids)
        record['players'] = [
            {'player_id': player_id, 'name': player_names[player_id]}
            for player_id in player_ids
        ]
        results.append(record)
    results.sort(key=lambda record: (
        record[sort_by] if sort_order == 'asc' else -record[sort_by],
        record['team_id'], tuple(record['player_ids']),
    ))
    return results[:limit] if limit is not None and limit > 0 else results
