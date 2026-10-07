import { apiClient } from "./client";
import type { LeaderboardRow } from "../types";

export async function fetchLeaderboard(): Promise<LeaderboardRow[]> {
  const { data } = await apiClient.get<LeaderboardRow[]>("/api/leaderboard");
  return data;
}
