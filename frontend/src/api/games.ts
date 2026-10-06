import { apiClient } from "./client";
import type { GamesResponse } from "../types";

export async function fetchGames(): Promise<GamesResponse> {
  const { data } = await apiClient.get<GamesResponse>("/api/games");
  return data;
}
