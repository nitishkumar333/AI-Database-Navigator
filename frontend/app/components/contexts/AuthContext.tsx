"use client";

import {
  createContext,
  useCallback,
  useEffect,
  useState,
  useRef,
} from "react";
import { host } from "../host";

export type AuthUser = {
  id: number;
  email: string;
  username: string;
};

export type OnboardingStatus = {
  has_connection: boolean;
  has_knowledge_base: boolean;
  onboarding_complete: boolean;
};

export const AuthContext = createContext<{
  user: AuthUser | null;
  token: string;
  isAuthenticated: boolean;
  isLoading: boolean;
  onboardingStatus: OnboardingStatus | null;
  login: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  register: (
    email: string,
    username: string,
    password: string
  ) => Promise<{ ok: boolean; error?: string }>;
  logout: () => void;
  getToken: () => string;
  clearAuth: () => void;
  refreshOnboardingStatus: () => Promise<OnboardingStatus | null>;
}>({
  user: null,
  token: "",
  isAuthenticated: false,
  isLoading: true,
  onboardingStatus: null,
  login: async () => ({ ok: false }),
  register: async () => ({ ok: false }),
  logout: () => {},
  getToken: () => "",
  clearAuth: () => {},
  refreshOnboardingStatus: async () => null,
});

export const AuthProvider = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);
  const [onboardingStatus, setOnboardingStatus] =
    useState<OnboardingStatus | null>(null);
  const initialized = useRef(false);

  const isAuthenticated = !!user && !!token;

  // On mount — check for stored token and validate
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    const stored = localStorage.getItem("auth_token");
    if (stored) {
      validateToken(stored);
    } else {
      setIsLoading(false);
    }
  }, []);

  const validateToken = async (t: string) => {
    try {
      const response = await fetch(`${host}/api/auth/me`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (response.ok) {
        const userData: AuthUser = await response.json();
        setToken(t);
        setUser(userData);
        localStorage.setItem("auth_token", t);
        // Fetch onboarding status
        await fetchOnboardingStatus(t);
      } else {
        // Token expired or invalid
        localStorage.removeItem("auth_token");
        setToken("");
        setUser(null);
      }
    } catch {
      localStorage.removeItem("auth_token");
      setToken("");
      setUser(null);
    }
    setIsLoading(false);
  };

  const fetchOnboardingStatus = async (
    t: string
  ): Promise<OnboardingStatus | null> => {
    try {
      const response = await fetch(`${host}/api/auth/onboarding-status`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (response.ok) {
        const data: OnboardingStatus = await response.json();
        setOnboardingStatus(data);
        return data;
      }
    } catch {
      // Silently fail
    }
    return null;
  };

  const refreshOnboardingStatus =
    async (): Promise<OnboardingStatus | null> => {
      const t = token || localStorage.getItem("auth_token") || "";
      if (!t) return null;
      return fetchOnboardingStatus(t);
    };

  const login = async (
    email: string,
    password: string
  ): Promise<{ ok: boolean; error?: string }> => {
    try {
      const response = await fetch(`${host}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (response.ok) {
        const data = await response.json();
        const newToken = data.access_token;
        localStorage.setItem("auth_token", newToken);
        setToken(newToken);
        // Fetch user info
        const meRes = await fetch(`${host}/api/auth/me`, {
          headers: { Authorization: `Bearer ${newToken}` },
        });
        if (meRes.ok) {
          const userData: AuthUser = await meRes.json();
          setUser(userData);
        }
        await fetchOnboardingStatus(newToken);
        return { ok: true };
      } else {
        const errData = await response.json().catch(() => ({}));
        return {
          ok: false,
          error: errData.detail || "Invalid credentials",
        };
      }
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  };

  const register = async (
    email: string,
    username: string,
    password: string
  ): Promise<{ ok: boolean; error?: string }> => {
    try {
      const response = await fetch(`${host}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, username, password }),
      });
      if (response.ok) {
        // Auto-login after registration
        return login(email, password);
      } else {
        const errData = await response.json().catch(() => ({}));
        return {
          ok: false,
          error: errData.detail || "Registration failed",
        };
      }
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  };

  const logout = () => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("selected_connection_id");
    localStorage.removeItem("selected_knowledge_base_id");
    setToken("");
    setUser(null);
    setOnboardingStatus(null);
  };

  const getToken = useCallback(() => {
    return token || localStorage.getItem("auth_token") || "";
  }, [token]);

  const clearAuth = () => {
    logout();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated,
        isLoading,
        onboardingStatus,
        login,
        register,
        logout,
        getToken,
        clearAuth,
        refreshOnboardingStatus,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
