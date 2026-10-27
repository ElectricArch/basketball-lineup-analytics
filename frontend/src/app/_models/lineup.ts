export interface LineupPlayer {
  player_id: string;
  name: string;
}

export interface LineupSummary {
  team_id: string;
  team_name: string;
  player_ids: string[];
  players: LineupPlayer[];
  total_possessions: number;
  offensive_possessions: number;
  offensive_points: number;
  offensive_shot_attempts: number;
  offensive_fg2_made: number;
  offensive_fg2_attempted: number;
  offensive_fg3_made: number;
  offensive_fg3_attempted: number;
  offensive_fg_made: number;
  offensive_fg_attempted: number;
  offensive_ft_made: number;
  offensive_ft_attempted: number;
  offensive_rebounds_offense: number;
  offensive_rebounds_defense: number;
  offensive_rebound_opportunities: number;
  offensive_assists: number;
  offensive_steals: number;
  offensive_turnovers: number;
  offensive_blocks: number;
  offensive_offensive_fouls: number;
  offensive_defensive_fouls: number;
  offensive_shooting_fouls: number;
  offensive_shot_attempt_points: number;
  offensive_ft_potential_points: number;
  offensive_transition_take_fouls: number;
  offensive_fg_pct: number;
  offensive_fg2_pct: number;
  offensive_fg3_pct: number;
  defensive_possessions: number;
  defensive_points: number;
  defensive_shot_attempts: number;
  defensive_fg2_made: number;
  defensive_fg2_attempted: number;
  defensive_fg3_made: number;
  defensive_fg3_attempted: number;
  defensive_fg_made: number;
  defensive_fg_attempted: number;
  defensive_ft_made: number;
  defensive_ft_attempted: number;
  defensive_rebounds_offense: number;
  defensive_rebounds_defense: number;
  defensive_rebound_opportunities: number;
  defensive_assists: number;
  defensive_steals: number;
  defensive_turnovers: number;
  defensive_blocks: number;
  defensive_offensive_fouls: number;
  defensive_defensive_fouls: number;
  defensive_shooting_fouls: number;
  defensive_shot_attempt_points: number;
  defensive_ft_potential_points: number;
  defensive_transition_take_fouls: number;
  defensive_fg_pct: number;
  defensive_fg2_pct: number;
  defensive_fg3_pct: number;
  offensive_rating: number;
  defensive_rating: number;
  net_rating: number;
  offensive_efg_pct: number;
  defensive_efg_pct: number;
  offensive_rebound_pct: number;
  defensive_rebound_pct: number;
  offensive_turnover_rate: number;
  opponent_turnover_rate: number;
}

export type LineupSortField =
    'total_possessions'
  | 'offensive_possessions'
  | 'defensive_possessions'
  | 'offensive_rating'
  | 'defensive_rating'
  | 'net_rating'
  | 'offensive_efg_pct'
  | 'defensive_efg_pct'
  | 'offensive_rebound_pct'
  | 'defensive_rebound_pct'
  | 'offensive_turnover_rate'
  | 'opponent_turnover_rate';

export type SortOrder = 'asc' | 'desc';

export interface LineupQueryOptions {
  lineup_size?: number;
  team_id?: string;
  player_id?: string;
  min_possessions?: number;
  sort_by?: LineupSortField;
  sort_order?: SortOrder;
  limit?: number | null;
}

export interface LineupApiResponse {
  endpoint: string;
  apiResponse: LineupSummary[];
}

export interface LineupTeam {
  team_id: string;
  team_name: string;
}

export interface CatalogPlayer extends LineupPlayer {
  team_id: string;
}
