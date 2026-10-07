import { apiClient } from "./client";
import type { Me } from "../types";

export interface RegisterInput {
  email: string;
  password: string;
  display_name: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
}

export async function register(input: RegisterInput): Promise<string> {
  const { data } = await apiClient.post<TokenResponse>("/api/auth/register", input);
  return data.access_token;
}

export async function login(input: LoginInput): Promise<string> {
  const { data } = await apiClient.post<TokenResponse>("/api/auth/login", input);
  return data.access_token;
}

export async function fetchRegistrationOpen(): Promise<boolean> {
  const { data } = await apiClient.get<{ open: boolean }>("/api/auth/registration");
  return data.open;
}

export async function fetchMe(): Promise<Me> {
  const { data } = await apiClient.get<Me>("/api/auth/me");
  return data;
}
