import { apiClient } from "./client";
import type { GamesResponse, Sport } from "../types";

export async function fetchSports(): Promise<Sport[]> {
  const { data } = await apiClient.get<Sport[]>("/api/sports");
  return data;
}

export async function fetchGames(sport: string): Promise<GamesResponse> {
  const { data } = await apiClient.get<GamesResponse>("/api/games", { params: { sport } });
  return data;
}
