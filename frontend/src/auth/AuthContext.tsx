import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fetchMe, login as loginRequest, register as registerRequest } from "../api/auth";
import type { LoginInput, RegisterInput } from "../api/auth";
import { TOKEN_STORAGE_KEY } from "../api/client";
import type { Me } from "../types";

interface AuthContextValue {
  me: Me | null;
  isLoading: boolean;
  login: (input: LoginInput) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => void;
  /** Re-fetch the current user, e.g. after a bet changes the balance. */
  refreshMe: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadMe = useCallback(async () => {
    const token = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (!token) {
      setMe(null);
      setIsLoading(false);
      return;
    }
    try {
      setMe(await fetchMe());
    } catch {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      setMe(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  const login = useCallback(
    async (input: LoginInput) => {
      const token = await loginRequest(input);
      localStorage.setItem(TOKEN_STORAGE_KEY, token);
      await loadMe();
    },
    [loadMe],
  );

  const register = useCallback(
    async (input: RegisterInput) => {
      const token = await registerRequest(input);
      localStorage.setItem(TOKEN_STORAGE_KEY, token);
      await loadMe();
    },
    [loadMe],
  );

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setMe(null);
  }, []);

  return (
    <AuthContext.Provider value={{ me, isLoading, login, register, logout, refreshMe: loadMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
