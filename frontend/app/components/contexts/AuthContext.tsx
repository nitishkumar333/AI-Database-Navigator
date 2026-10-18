"use client";

import { createContext, useEffect, useState, useRef } from "react";
import { apiFetch, TOKEN_KEY } from "../../utils/api";
// Also installs the fetch wrapper that reports the API's rate limit.
import {
  RATE_LIMIT_LOGOUT_EVENT,
  RateLimitLogoutDetail,
} from "../../utils/rateLimitLogout";

export type AuthUser = {
  id: number;
  email: string;
  username: string;
  is_guest?: boolean;
};

export type OnboardingStatus = {
  has_connection: boolean;
  has_knowledge_base: boolean;
  onboarding_complete: boolean;
};

type AuthResult = { ok: boolean; error?: string };

export const AuthContext = createContext<{
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  onboardingStatus: OnboardingStatus | null;
  // Why the user was signed out (e.g. rate limit), shown on the login page.
  signedOutNotice: string;
  login: (email: string, password: string) => Promise<AuthResult>;
  register: (
    email: string,
    username: string,
    password: string
  ) => Promise<AuthResult>;
  guestLogin: () => Promise<AuthResult>;
  logout: () => void;
  refreshOnboardingStatus: () => Promise<OnboardingStatus | null>;
}>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  onboardingStatus: null,
  signedOutNotice: "",
  login: async () => ({ ok: false }),
  register: async () => ({ ok: false }),
  guestLogin: async () => ({ ok: false }),
  logout: () => {},
  refreshOnboardingStatus: async () => null,
});

const errorDetail = async (response: Response, fallback: string) => {
  const data = await response.json().catch(() => ({}));
  return data.detail || fallback;
};

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
  const [signedOutNotice, setSignedOutNotice] = useState("");
  const initialized = useRef(false);

  const isAuthenticated = !!user && !!token;

  // The API's own rate limit refused a request: sign the user out.
  useEffect(() => {
    const onRateLimited = (event: Event) => {
      const { seconds } = (event as CustomEvent<RateLimitLogoutDetail>).detail;
      logout();
      setSignedOutNotice(
        "You were signed out because of too many requests. " +
          (seconds
            ? `Try again in ${seconds} second${seconds === 1 ? "" : "s"}.`
            : "Please wait a moment and try again.")
      );
    };
    window.addEventListener(RATE_LIMIT_LOGOUT_EVENT, onRateLimited);
    return () => window.removeEventListener(RATE_LIMIT_LOGOUT_EVENT, onRateLimited);
    // logout only uses state setters, so the first one stays valid.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // On mount — check for stored token and validate
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    const stored = localStorage.getItem(TOKEN_KEY);
    if (stored) {
      validateToken(stored);
    } else {
      setIsLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const validateToken = async (t: string) => {
    try {
      const response = await apiFetch("/api/auth/me", { token: t });
      if (response.ok) {
        setToken(t);
        setUser(await response.json());
        await fetchOnboardingStatus(t);
      } else {
        // Token expired or invalid
        clearToken();
      }
    } catch {
      clearToken();
    }
    setIsLoading(false);
  };

  const clearToken = () => {
    localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setUser(null);
  };

  const fetchOnboardingStatus = async (
    t?: string
  ): Promise<OnboardingStatus | null> => {
    try {
      const response = await apiFetch("/api/auth/onboarding-status", { token: t });
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

  const refreshOnboardingStatus = async () =>
    localStorage.getItem(TOKEN_KEY) ? fetchOnboardingStatus() : null;

  // Signs in with a token from login or guest login.
  const startSession = async (newToken: string) => {
    localStorage.setItem(TOKEN_KEY, newToken);
    setToken(newToken);
    const meRes = await apiFetch("/api/auth/me", { token: newToken });
    if (meRes.ok) setUser(await meRes.json());
    await fetchOnboardingStatus(newToken);
    setSignedOutNotice("");
  };

  const login = async (email: string, password: string): Promise<AuthResult> => {
    try {
      const response = await apiFetch("/api/auth/login", {
        method: "POST",
        body: { email, password },
      });
      if (!response.ok) {
        return { ok: false, error: await errorDetail(response, "Invalid credentials") };
      }
      await startSession((await response.json()).access_token);
      return { ok: true };
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  };

  const register = async (
    email: string,
    username: string,
    password: string
  ): Promise<AuthResult> => {
    try {
      const response = await apiFetch("/api/auth/register", {
        method: "POST",
        body: { email, username, password },
      });
      if (!response.ok) {
        return { ok: false, error: await errorDetail(response, "Registration failed") };
      }
      // Auto-login after registration
      return login(email, password);
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  };

  const guestLogin = async (): Promise<AuthResult> => {
    try {
      // Clear any previous connection/KB selections so fresh guest defaults are selected
      localStorage.removeItem("selected_connection_id");
      localStorage.removeItem("selected_knowledge_base_id");

      const response = await apiFetch("/api/auth/guest-login", { method: "POST" });
      if (!response.ok) {
        return { ok: false, error: await errorDetail(response, "Guest login failed") };
      }
      await startSession((await response.json()).access_token);
      return { ok: true };
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  };

  const logout = () => {
    clearToken();
    localStorage.removeItem("selected_connection_id");
    localStorage.removeItem("selected_knowledge_base_id");
    setOnboardingStatus(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated,
        isLoading,
        onboardingStatus,
        signedOutNotice,
        login,
        register,
        guestLogin,
        logout,
        refreshOnboardingStatus,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
