"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Connection } from "@/app/types/objects";
import { apiFetch } from "../../utils/api";
import { ToastContext } from "./ToastContext";
import { AuthContext } from "./AuthContext";
import { QueryContext } from "./QueryContext";

const FALLBACK_SUGGESTIONS = [
  "Show all tables in the database",
  "How many records are in each table?",
  "Show me the first 10 rows",
  "What columns are available?",
];

export const CollectionContext = createContext<{
  connections: Connection[];
  /** True once the connection list has been fetched (connections may be empty). */
  connectionsLoaded: boolean;
  fetchConnections: () => void;
  fetchSuggestions: (connectionId: number, knowledgeBaseId?: number | null, forceRefresh?: boolean) => Promise<string[]>;
  clearSuggestionsCache: () => void;
}>({
  connections: [],
  connectionsLoaded: false,
  fetchConnections: () => {},
  fetchSuggestions: async () => [],
  clearSuggestionsCache: () => {},
});

export const CollectionProvider = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  const { showSuccessToast } = useContext(ToastContext);
  const { logout, isAuthenticated } = useContext(AuthContext);
  const { backendOnline } = useContext(QueryContext);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionsLoaded, setConnectionsLoaded] = useState(false);

  // Cache for suggestions keyed by "connId_kbId"
  const suggestionsCache = useRef<Record<string, string[]>>({});

  const initialFetch = useRef(false);

  // Reset all connection state when user logs out
  useEffect(() => {
    if (!isAuthenticated) {
      setConnections([]);
      setConnectionsLoaded(false);
      suggestionsCache.current = {};
      initialFetch.current = false;
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (initialFetch.current || !backendOnline || !isAuthenticated) return;
    initialFetch.current = true;
    fetchConnections();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendOnline, isAuthenticated]);

  const fetchConnections = async () => {
    try {
      const response = await apiFetch("/api/connections");
      if (response.ok) {
        const data: Connection[] = await response.json();
        setConnections(data);
        setConnectionsLoaded(true);
        if (data.length > 0) {
          showSuccessToast(`${data.length} connections loaded`);
        }
      } else if (response.status === 401) {
        logout();
      }
    } catch (e) {
      console.error("Failed to fetch connections:", e);
    }
  };

  const fetchSuggestions = async (
    connectionId: number,
    knowledgeBaseId?: number | null,
    forceRefresh?: boolean
  ): Promise<string[]> => {
    const cacheKey = `${connectionId}_${knowledgeBaseId || "all"}`;
    if (!forceRefresh && suggestionsCache.current[cacheKey]) {
      return suggestionsCache.current[cacheKey];
    }

    try {
      const response = await apiFetch("/api/suggestions/initial", {
        method: "POST",
        body: {
          connection_id: connectionId,
          knowledge_base_id: knowledgeBaseId || null,
          force_refresh: forceRefresh || false,
        },
      });

      if (response.ok) {
        const data = await response.json();
        const suggestions = data.suggestions || [];
        suggestionsCache.current[cacheKey] = suggestions;
        return suggestions;
      }
    } catch (e) {
      console.error("Failed to fetch suggestions:", e);
    }

    return FALLBACK_SUGGESTIONS;
  };

  const clearSuggestionsCache = () => {
    suggestionsCache.current = {};
  };

  return (
    <CollectionContext.Provider
      value={{
        connections,
        connectionsLoaded,
        fetchConnections,
        fetchSuggestions,
        clearSuggestionsCache,
      }}
    >
      {children}
    </CollectionContext.Provider>
  );
};
