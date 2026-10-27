"""Small dependency-free bounds shared by request and fixture validation."""
MAX_RESULTS = 100
MAX_POSSESSIONS = 1000
MAX_PLAYERS = 96
MAX_TEAMS = 8
MAX_QUERY_LENGTH = 2048
NUMERIC_PARAMS = {"lineup_size", "min_possessions", "limit"}

def bounded_http_limit(value):
    try:
        limit = int(value)
    except (ValueError, TypeError):
        return MAX_RESULTS
    return min(limit, MAX_RESULTS) if limit > 0 else MAX_RESULTS

def validate_query(raw_query, pairs):
    if len(raw_query) > MAX_QUERY_LENGTH or len(pairs) > 16:
        raise ValueError("Request query is too large")
    for key, value in pairs:
        if len(key) > 64 or len(value) > (24 if key in NUMERIC_PARAMS else 64):
            raise ValueError("Request parameter is too large")

def validate_five_players(values, team_id, player_teams):
    if not isinstance(values, (list, tuple)) or len(values) != 5:
        raise ValueError("Every possession side requires exactly five players")
    ids = [str(value) for value in values]
    if len(set(ids)) != 5 or any(player_teams.get(player) != str(team_id) for player in ids):
        raise ValueError("Possession players must be distinct known team members")

