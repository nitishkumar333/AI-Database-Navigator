"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { apiFetch, getStoredToken } from "../../utils/api";
import { AuthContext } from "./AuthContext";
import { ToastContext } from "./ToastContext";

// Response of POST /api/query/chat (or a failure shaped like one).
export type QueryResult = {
  success: boolean;
  error?: string;
  response_text?: string;
  generated_sql?: string;
  rows?: Record<string, unknown>[];
  columns?: string[];
};

export const QueryContext = createContext<{
  backendOnline: boolean;
  sendQuery: (
    question: string,
    connection_id?: number | null,
    knowledge_base_id?: number | null,
    conversation_id?: string | null,
    query_id?: string | null
  ) => Promise<QueryResult>;
}>({
  backendOnline: false,
  sendQuery: async () => ({ success: false }),
});

export const QueryProvider = ({ children }: { children: React.ReactNode }) => {
  const [backendOnline, setBackendOnline] = useState(false);
  const { logout } = useContext(AuthContext);
  const { showSuccessToast } = useContext(ToastContext);
  const announced = useRef(false);

  // Health check polling
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await apiFetch("/health", { token: "" });
        setBackendOnline(response.ok);
      } catch {
        setBackendOnline(false);
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 120000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (announced.current || !backendOnline) return;
    announced.current = true;
    showSuccessToast("Connected to SQLNav");
  }, [backendOnline, showSuccessToast]);

  const sendQuery = async (
    question: string,
    connection_id?: number | null,
    knowledge_base_id?: number | null,
    conversation_id?: string | null,
    query_id?: string | null
  ): Promise<QueryResult> => {
    if (!getStoredToken()) {
      return {
        success: false,
        error: "Not authenticated",
        response_text: "**Error:** Please log in first.",
      };
    }

    try {
      const response = await apiFetch("/api/query/chat", {
        method: "POST",
        body: {
          question,
          connection_id: connection_id || null,
          knowledge_base_id: knowledge_base_id || null,
          conversation_id: conversation_id || null,
          query_id: query_id || null,
        },
      });

      if (!response.ok) {
        if (response.status === 401) {
          logout();
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
    <QueryContext.Provider value={{ backendOnline, sendQuery }}>
      {children}
    </QueryContext.Provider>
  );
};
