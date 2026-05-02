"use client";

import { createContext, useEffect, useState, useCallback } from "react";
import { host } from "../host";

export const QueryContext = createContext<{
  backendOnline: boolean;
  sendQuery: (
    question: string,
    connection_id?: number | null
  ) => Promise<any | null>;
  getToken: () => string;
}>({
  backendOnline: false,
  sendQuery: async () => null,
  getToken: () => "",
});

export const QueryProvider = ({ children }: { children: React.ReactNode }) => {
  const [backendOnline, setBackendOnline] = useState(false);
  const [token, setToken] = useState<string>("");

  // Auto-auth on mount
  useEffect(() => {
    const stored = localStorage.getItem("auth_token");
    if (stored) {
      setToken(stored);
      checkHealth();
    } else {
      autoAuth();
    }
  }, []);

  // Health check polling
  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  const checkHealth = async () => {
    try {
      const response = await fetch(`${host}/health`);
      setBackendOnline(response.ok);
    } catch {
      setBackendOnline(false);
    }
  };

  const autoAuth = async () => {
    try {
      // Try to register
      let response = await fetch(`${host}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: "admin@dataanalyst.local",
          username: "admin",
          password: "admin123",
        }),
      });

      // Whether registration succeeded or not, try to login
      response = await fetch(`${host}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: "admin@dataanalyst.local",
          password: "admin123",
        }),
      });

      if (response.ok) {
        const data = await response.json();
        localStorage.setItem("auth_token", data.access_token);
        setToken(data.access_token);
      }
    } catch (e) {
      console.error("Auto-auth failed:", e);
    }
  };

  const getToken = useCallback(() => {
    return token || localStorage.getItem("auth_token") || "";
  }, [token]);

  const sendQuery = async (
    question: string,
    connection_id?: number | null
  ): Promise<any | null> => {
    const authToken = getToken();
    if (!authToken) {
      await autoAuth();
    }
    const currentToken = getToken();

    try {
      const response = await fetch(`${host}/api/query/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${currentToken}`,
        },
        body: JSON.stringify({
          question,
          connection_id: connection_id || null,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        return {
          success: false,
          error: errorData.detail || `HTTP ${response.status}`,
          response_text: `**Error:** ${errorData.detail || `Request failed with status ${response.status}`}`,
        };
      }

      return await response.json();
    } catch (e) {
      return {
        success: false,
        error: String(e),
        response_text: `**Error:** Failed to connect to backend. ${String(e)}`,
      };
    }
  };

  return (
    <QueryContext.Provider value={{ backendOnline, sendQuery, getToken }}>
      {children}
    </QueryContext.Provider>
  );
};
