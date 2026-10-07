import axios from "axios";
import { apiClient } from "./client";
import type { Bet, LedgerEntry, OddsLine } from "../types";

export interface PlaceBetResult {
  bet: Bet;
  balance_cents: number;
}

export interface LineChange {
  odds_line_id: string;
  price_american: number;
  point: number | null;
}

/** Thrown when one or more lines moved between viewing them and placing the bet. */
export class OddsChangedError extends Error {
  changes: LineChange[];

  constructor(changes: LineChange[]) {
    super("The odds have changed");
    this.changes = changes;
  }
}

/** One line is a single bet; several is a parlay. */
export async function placeBet(lines: OddsLine[], stakeCents: number): Promise<PlaceBetResult> {
  try {
    const { data } = await apiClient.post<PlaceBetResult>("/api/bets", {
      legs: lines.map((line) => ({
        odds_line_id: line.id,
        expected_price_american: line.price_american,
        expected_point: line.point,
      })),
      stake_cents: stakeCents,
    });
    return data;
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.status === 409) {
      throw new OddsChangedError(err.response.data.detail.changes);
    }
    throw err;
  }
}

export async function fetchBets(state: "open" | "settled"): Promise<Bet[]> {
  const { data } = await apiClient.get<Bet[]>("/api/bets", { params: { state } });
  return data;
}

export async function fetchLedger(limit = 50): Promise<LedgerEntry[]> {
  const { data } = await apiClient.get<LedgerEntry[]>("/api/wallet/ledger", { params: { limit } });
  return data;
}
