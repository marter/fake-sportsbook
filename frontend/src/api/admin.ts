import { apiClient } from "./client";
import type { AdminUser, Bet, LedgerEntry, StuckGame } from "../types";

export async function fetchUsers(): Promise<AdminUser[]> {
  const { data } = await apiClient.get<AdminUser[]>("/api/admin/users");
  return data;
}

export type Adjustment =
  | { amount_cents: number; note?: string }
  | { set_balance_cents: number; note?: string };

export async function adjustBalance(userId: string, adjustment: Adjustment): Promise<LedgerEntry> {
  const { data } = await apiClient.post<LedgerEntry>(
    `/api/admin/users/${userId}/adjust`,
    adjustment,
  );
  return data;
}

export async function fetchUserBets(
  userId: string,
  state: "open" | "settled",
): Promise<{ user: AdminUser; bets: Bet[] }> {
  const { data } = await apiClient.get<{ user: AdminUser; bets: Bet[] }>(
    `/api/admin/users/${userId}/bets`,
    { params: { state } },
  );
  return data;
}

export async function voidBet(betId: string, note?: string): Promise<Bet> {
  const { data } = await apiClient.post<Bet>(`/api/admin/bets/${betId}/void`, { note });
  return data;
}

export async function markVerified(userId: string): Promise<AdminUser> {
  const { data } = await apiClient.post<AdminUser>(`/api/admin/users/${userId}/verify`);
  return data;
}

/** Permanently deletes the account with all its bets and history. */
export async function deleteUser(userId: string): Promise<void> {
  await apiClient.delete(`/api/admin/users/${userId}`);
}

export async function fetchStuckGames(): Promise<StuckGame[]> {
  const { data } = await apiClient.get<StuckGame[]>("/api/admin/stuck-games");
  return data;
}
