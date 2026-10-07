export interface User {
  id: string;
  email: string;
  display_name: string;
  balance_cents: number;
  is_admin: boolean;
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

export type BetStatus = "pending" | "won" | "lost" | "push" | "void";
export type LegResult = "pending" | "won" | "lost" | "push";

export interface BetGame {
  id: string;
  home_team: string;
  away_team: string;
  commence_time: string;
  completed: boolean;
  home_score: number | null;
  away_score: number | null;
}

export interface BetLeg {
  market: Market;
  outcome: string;
  price_american: number;
  point: number | null;
  result: LegResult;
  game: BetGame;
}

export interface Bet {
  id: string;
  stake_cents: number;
  potential_payout_cents: number;
  payout_cents: number | null;
  status: BetStatus;
  created_at: string;
  settled_at: string | null;
  legs: BetLeg[];
}

export type LedgerKind =
  | "signup_bonus"
  | "bet_stake"
  | "bet_payout"
  | "bet_refund"
  | "admin_adjustment";

export interface LedgerEntry {
  id: string;
  amount_cents: number;
  balance_after_cents: number;
  kind: LedgerKind;
  bet_id: string | null;
  note: string | null;
  created_at: string;
}

export interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  balance_cents: number;
  is_admin: boolean;
  created_at: string;
}

/** A tapped odds button: the line plus the game it belongs to. */
export interface Selection {
  game: Game;
  line: OddsLine;
}
