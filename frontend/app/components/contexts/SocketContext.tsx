"use client";

import { createContext, useEffect, useState, useContext, useCallback } from "react";
import { host } from "../host";
import { AuthContext } from "./AuthContext";

export const QueryContext = createContext<{
  backendOnline: boolean;
  sendQuery: (
    question: string,
    connection_id?: number | null,
    knowledge_base_id?: number | null,
    conversation_id?: string | null,
    query_id?: string | null
  ) => Promise<any | null>;
  getToken: () => string;
  clearAuth: () => void;
}>({
  backendOnline: false,
  sendQuery: async () => null,
  getToken: () => "",
  clearAuth: () => {},
});

export const QueryProvider = ({ children }: { children: React.ReactNode }) => {
  const [backendOnline, setBackendOnline] = useState(false);
  const { getToken, clearAuth } = useContext(AuthContext);

  // Health check polling
  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 60000);
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

  const sendQuery = async (
    question: string,
    connection_id?: number | null,
    knowledge_base_id?: number | null,
    conversation_id?: string | null,
    query_id?: string | null
  ): Promise<any | null> => {
    const currentToken = getToken();
    if (!currentToken) {
      return {
        success: false,
        error: "Not authenticated",
        response_text: "**Error:** Please log in first.",
      };
    }

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
          knowledge_base_id: knowledge_base_id || null,
          conversation_id: conversation_id || null,
          query_id: query_id || null,
        }),
      });

      if (!response.ok) {
        if (response.status === 401) {
          clearAuth();
          return {
            success: false,
            error: "Session expired. Please log in again.",
            response_text: "Session expired. Please log in again.",
          };
        }
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
    <QueryContext.Provider value={{ backendOnline, sendQuery, getToken, clearAuth }}>
      {children}
    </QueryContext.Provider>
  );
};
