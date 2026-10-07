import { apiClient } from "./client";
import type { AdminUser, LedgerEntry } from "../types";

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
