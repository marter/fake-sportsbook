import axios from "axios";
import { apiClient } from "./client";
import type { Bet, LedgerEntry, OddsLine } from "../types";

export interface PlaceBetResult {
  bet: Bet;
  balance_cents: number;
}

/** Thrown when the line moved between viewing it and placing the bet. */
export class OddsChangedError extends Error {
  price_american: number;
  point: number | null;

  constructor(price_american: number, point: number | null) {
    super("The odds have changed");
    this.price_american = price_american;
    this.point = point;
  }
}

export async function placeBet(line: OddsLine, stakeCents: number): Promise<PlaceBetResult> {
  try {
    const { data } = await apiClient.post<PlaceBetResult>("/api/bets", {
      odds_line_id: line.id,
      stake_cents: stakeCents,
      expected_price_american: line.price_american,
      expected_point: line.point,
    });
    return data;
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.status === 409) {
      const detail = err.response.data.detail;
      throw new OddsChangedError(detail.price_american, detail.point);
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
