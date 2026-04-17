"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Collection } from "@/app/types/objects";
import { SessionContext } from "./SessionContext";
import { ToastContext } from "./ToastContext";
import { AuthContext } from "./AuthContext";
import { QueryContext } from "./SocketContext";
import { host } from "../host";

export type Connection = {
  id: number;
  name: string;
  host: string;
  port: number;
  db_name: string;
  username: string;
  created_at?: string;
};

export const CollectionContext = createContext<{
  collections: Collection[];
  connections: Connection[];
  fetchCollections: () => void;
  loadingCollections: boolean;
  fetchSuggestions: (connectionId: number, knowledgeBaseId?: number | null, forceRefresh?: boolean) => Promise<string[]>;
  clearSuggestionsCache: () => void;
}>({
  collections: [],
  connections: [],
  fetchCollections: () => {},
  loadingCollections: false,
  fetchSuggestions: async () => [],
  clearSuggestionsCache: () => {},
});

export const CollectionProvider = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  const { id, fetchCollectionFlag, initialized } = useContext(SessionContext);
  const { showSuccessToast } = useContext(ToastContext);
  const { getToken, clearAuth, isAuthenticated } = useContext(AuthContext);
  const { backendOnline } = useContext(QueryContext);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loadingCollections, setLoadingCollections] = useState(false);

  // Cache for suggestions keyed by "connId_kbId"
  const suggestionsCache = useRef<Record<string, string[]>>({});

  const initialFetch = useRef(false);

  useEffect(() => {
    if (initialFetch.current || !id || !backendOnline || !isAuthenticated) return;
    initialFetch.current = true;
    fetchCollections();
  }, [id, backendOnline, isAuthenticated]);

  useEffect(() => {
    if (initialFetch.current) {
      fetchCollections();
    }
  }, [fetchCollectionFlag]);

  const fetchCollections = async () => {
    const token = getToken();
    if (!token) return;
    setLoadingCollections(true);
    try {
      const response = await fetch(`${host}/api/connections`, {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
      if (response.ok) {
        const rawConnections: Connection[] = await response.json();
        setConnections(rawConnections);
        // Map connections to Collection type for compatibility
        const mapped: Collection[] = rawConnections.map(
          (conn) => ({
            name: `${conn.name} (${conn.db_name}@${conn.host})`,
            total: 0,
            vectorizer: {
              fields: {},
              global: {
                named_vector: "default",
                vectorizer: "none",
                model: "none",
              },
            },
            processed: true,
            prompts: [],
          })
        );
        setCollections(mapped);
        if (mapped.length > 0) {
          showSuccessToast(`${mapped.length} connections loaded`);
        }
      } else if (response.status === 401) {
        clearAuth();
      }
    } catch (e) {
      console.error("Failed to fetch collections:", e);
    }
    setLoadingCollections(false);
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
      const token = getToken();
      if (!token) return [];

      const response = await fetch(`${host}/api/suggestions/initial`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          connection_id: connectionId,
          knowledge_base_id: knowledgeBaseId || null,
        }),
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

    // Fallback
    return [
      "Show all tables in the database",
      "How many records are in each table?",
      "Show me the first 10 rows",
      "What columns are available?",
    ];
  };

  const clearSuggestionsCache = () => {
    suggestionsCache.current = {};
  };

  return (
    <CollectionContext.Provider
      value={{
        collections,
        connections,
        fetchCollections,
        loadingCollections,
        fetchSuggestions,
        clearSuggestionsCache,
      }}
    >
      {children}
    </CollectionContext.Provider>
  );
};
