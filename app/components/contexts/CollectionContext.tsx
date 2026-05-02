"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Collection } from "@/app/types/objects";
import { SessionContext } from "./SessionContext";
import { ToastContext } from "./ToastContext";
import { QueryContext } from "./SocketContext";
import { host } from "../host";

export const CollectionContext = createContext<{
  collections: Collection[];
  fetchCollections: () => void;
  loadingCollections: boolean;
  getRandomPrompts: (amount: number) => string[];
}>({
  collections: [],
  fetchCollections: () => {},
  loadingCollections: false,
  getRandomPrompts: () => [],
});

export const CollectionProvider = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  const { id, fetchCollectionFlag, initialized } = useContext(SessionContext);
  const { showSuccessToast } = useContext(ToastContext);
  const { getToken, backendOnline } = useContext(QueryContext);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loadingCollections, setLoadingCollections] = useState(false);

  const initialFetch = useRef(false);

  useEffect(() => {
    if (initialFetch.current || !id || !backendOnline) return;
    initialFetch.current = true;
    fetchCollections();
  }, [id, backendOnline]);

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
        const connections = await response.json();
        // Map connections to Collection type for compatibility
        const mapped: Collection[] = connections.map(
          (conn: {
            id: number;
            name: string;
            host: string;
            port: number;
            db_name: string;
            username: string;
          }) => ({
            name: `${conn.name} (${conn.db_name}@${conn.host})`,
            total: 0, // Will be populated when user clicks into it
            vectorizer: {
              fields: {},
              global: {
                named_vector: "default",
                vectorizer: "none",
                model: "none",
              },
            },
            processed: true,
            prompts: [
              `Show all tables in ${conn.name}`,
              `How many records are in each table?`,
              `Show me the first 10 rows`,
            ],
          })
        );
        setCollections(mapped);
        if (mapped.length > 0) {
          showSuccessToast(`${mapped.length} connections loaded`);
        }
      }
    } catch (e) {
      console.error("Failed to fetch collections:", e);
    }
    setLoadingCollections(false);
  };

  const getRandomPrompts = (amount: number = 4) => {
    const allPrompts = collections.reduce((acc: string[], collection) => {
      return acc.concat(collection.prompts || []);
    }, []);
    const shuffled = allPrompts.sort(() => 0.5 - Math.random());
    return shuffled.slice(0, amount);
  };

  return (
    <CollectionContext.Provider
      value={{
        collections,
        fetchCollections,
        loadingCollections,
        getRandomPrompts,
      }}
    >
      {children}
    </CollectionContext.Provider>
  );
};
