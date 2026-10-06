export interface User {
  id: string;
  email: string;
  display_name: string;
  balance_cents: number;
}

export type Me = User;

export type Market = "h2h" | "spreads" | "totals";

export interface OddsLine {
  id: string;
  market: Market;
  outcome: string;
  price_american: number;
  point: number | null;
}

export interface Game {
  id: string;
  home_team: string;
  away_team: string;
  commence_time: string;
  odds_lines: OddsLine[];
}

export interface GamesResponse {
  odds_updated_at: string | null;
  games: Game[];
}
