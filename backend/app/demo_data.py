"""Original deterministic demonstration data; no external records or identities."""
from datetime import date
from math import isfinite
from uuid import NAMESPACE_DNS, UUID, uuid5

from app.safety import MAX_PLAYERS, MAX_POSSESSIONS, MAX_TEAMS, validate_five_players

NAMESPACE = uuid5(NAMESPACE_DNS, "lineup-demo.synthetic.example")
VERSION = 1
COUNTING_FIELDS = (
    "points", "shot_attempts", "fg2_made", "fg2_attempted", "fg3_made", "fg3_attempted",
    "fg_made", "fg_attempted", "ft_made", "ft_attempted", "rebounds_offense",
    "rebounds_defense", "rebound_opportunities", "assists", "steals", "turnovers",
    "blocks", "offensive_fouls", "defensive_fouls", "shooting_fouls",
    "shot_attempt_points", "ft_potential_points", "transition_take_fouls",
)

def identity(label):
    return str(uuid5(NAMESPACE, label))

def build_demo_data():
    labels = ("North", "Central", "South")
    teams = [{"id": identity("team/" + label), "name": label + " Unit"} for label in labels]
    players = [
        {"id": identity("player/" + label + "/" + str(number)),
         "team_id": teams[t]["id"], "name": label + " Player " + str(number + 1).zfill(2)}
        for t, label in enumerate(labels) for number in range(7)
    ]
    roster = [[p["id"] for p in players if p["team_id"] == team["id"]] for team in teams]
    games = [{"id": identity("game/" + str(i)), "date": date(2026, 1, i + 1).isoformat()} for i in range(3)]
    visits = {(t, side): 0 for t in range(3) for side in ("offensive", "defensive")}

    def unit(team, side):
        n = visits[team, side]
        visits[team, side] += 1
        r = roster[team]
        if n < 8:
            return r[:5]
        if side == "offensive" and n >= 10:
            return r[:3] + r[5:7]
        return r[:4] + [r[5]]

    possessions = []
    events = (
        {"fg2_made": 1, "fg2_attempted": 1, "fg_made": 1, "fg_attempted": 1,
         "points": 2, "shot_attempts": 1, "shot_attempt_points": 2, "assists": 1},
        {"fg3_attempted": 1, "fg_attempted": 1, "shot_attempts": 1,
         "rebounds_defense": 1, "rebound_opportunities": 1},
        {"fg3_made": 1, "fg3_attempted": 1, "fg_made": 1, "fg_attempted": 1,
         "points": 3, "shot_attempts": 1, "shot_attempt_points": 3, "assists": 1},
        {"turnovers": 1, "steals": 1},
        {"fg2_attempted": 1, "fg_attempted": 1, "shot_attempts": 1,
         "rebounds_offense": 1, "rebound_opportunities": 1},
        {"ft_made": 1, "ft_attempted": 2, "points": 1, "ft_potential_points": 2,
         "shooting_fouls": 1, "defensive_fouls": 1},
    )
    for game_index, (a, b) in enumerate(((0, 1), (1, 2), (2, 0))):
        for index in range(12):
            number = game_index * 12 + index
            offense, defense = (a, b) if index % 2 == 0 else (b, a)
            row = {field: 0 for field in COUNTING_FIELDS}
            row.update(events[number % 6])
            row.update(
                id=identity("possession/" + str(number)), game_id=games[game_index]["id"],
                offensive_team_id=teams[offense]["id"], defensive_team_id=teams[defense]["id"],
                offensive_player_ids=unit(offense, "offensive"),
                defensive_player_ids=unit(defense, "defensive"), period=1, seconds=12.0,
            )
            possessions.append(row)
    data = {"teams": teams, "players": players, "games": games, "possessions": possessions}
    validate_demo_data(data)
    return data

def validate_demo_data(data):
    limits = {"teams": MAX_TEAMS, "players": MAX_PLAYERS, "possessions": MAX_POSSESSIONS, "games": 1000}
    for group, maximum in limits.items():
        rows = data[group]
        if len(rows) > maximum or len({r["id"] for r in rows}) != len(rows):
            raise ValueError("Invalid demo cardinality or duplicate identity")
        for row in rows:
            UUID(row["id"])
    teams = {r["id"] for r in data["teams"]}
    games = {r["id"] for r in data["games"]}
    player_teams = {r["id"]: r["team_id"] for r in data["players"]}
    if any(team not in teams for team in player_teams.values()):
        raise ValueError("Unknown demo team")
    for game in data["games"]:
        date.fromisoformat(game["date"])
    for row in data["possessions"]:
        if row["game_id"] not in games or row["offensive_team_id"] == row["defensive_team_id"]:
            raise ValueError("Invalid demo game or opposing teams")
        for side in ("offensive", "defensive"):
            if row[side + "_team_id"] not in teams:
                raise ValueError("Unknown possession team")
            validate_five_players(row[side + "_player_ids"], row[side + "_team_id"], player_teams)
        for field in COUNTING_FIELDS:
            if type(row[field]) is not int or row[field] < 0:
                raise ValueError("Demo counts must be nonnegative integers")
        if not isfinite(row["seconds"]) or row["seconds"] < 0 or row["period"] < 1:
            raise ValueError("Invalid demo timing")
        for shot in ("fg2", "fg3", "fg", "ft"):
            if row[shot + "_made"] > row[shot + "_attempted"]:
                raise ValueError("Demo makes exceed attempts")
        if (row["fg_made"] != row["fg2_made"] + row["fg3_made"] or
            row["fg_attempted"] != row["fg2_attempted"] + row["fg3_attempted"] or
            row["points"] != 2 * row["fg2_made"] + 3 * row["fg3_made"] + row["ft_made"]):
            raise ValueError("Inconsistent demo shooting totals")
