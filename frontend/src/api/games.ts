import { apiClient } from "./client";
import type { GameProps, GamesResponse, Sport } from "../types";

export async function fetchSports(): Promise<Sport[]> {
  const { data } = await apiClient.get<Sport[]>("/api/sports");
  return data;
}

export async function fetchGames(sport: string): Promise<GamesResponse> {
  const { data } = await apiClient.get<GamesResponse>("/api/games", { params: { sport } });
  return data;
}

export async function fetchGameProps(gameId: string): Promise<GameProps> {
  const { data } = await apiClient.get<GameProps>(`/api/games/${gameId}/props`);
  return data;
}
