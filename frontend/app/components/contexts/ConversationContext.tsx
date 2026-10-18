"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Conversation, initialConversation } from "../types";
import {
  Query,
  Message,
  ResultPayload,
  ResponsePayload,
} from "@/app/types/chat";
import { v4 as uuidv4 } from "uuid";
import { SessionContext } from "./SessionContext";
import { RouterContext } from "./RouterContext";
import { AuthContext } from "./AuthContext";
import { host } from "../host";
import { detectProductData, mapRowsToProducts } from "@/app/utils/detectProductdata";

// One entry of GET /api/conversations.
type ConversationSummary = {
  id: string;
  name?: string;
  created_at?: string | null;
  message_count?: number;
};

export const ConversationContext = createContext<{
  conversations: Conversation[];
  currentConversation: string | null;
  creatingNewConversation: boolean;
  startNewConversation: (openChat?: boolean) => void;
  removeConversation: (id: string) => void;
  dropConversations: (ids: string[]) => void;
  selectConversation: (id: string) => void;
  setConversationStatus: (status: string, conversationId: string) => void;
  setConversationTitle: (title: string, conversationId: string) => void;
  addMessageToConversation: (
    messages: Message[],
    conversationId: string,
    queryId: string
  ) => void;
  addQueryToConversation: (
    conversationId: string,
    query: string,
    query_id: string
  ) => void;
  finishQuery: (conversationId: string, queryId: string) => void;
  addSuggestionToConversation: (
    conversationId: string,
    queryId: string,
    connectionId?: number | null,
    knowledgeBaseId?: number | null
  ) => void;
}>({
  conversations: [],
  currentConversation: null,
  creatingNewConversation: false,
  startNewConversation: () => {},
  removeConversation: () => {},
  dropConversations: () => {},
  selectConversation: () => {},
  setConversationStatus: () => {},
  setConversationTitle: () => {},
  addMessageToConversation: () => {},
  addQueryToConversation: () => {},
  finishQuery: () => {},
  addSuggestionToConversation: () => {},

});

export const ConversationProvider = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  const { id } = useContext(SessionContext);
  const { changePage, currentPage } = useContext(RouterContext);
  const { getToken, isAuthenticated, user } = useContext(AuthContext);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversation, setCurrentConversation] = useState<string | null>(
    null
  );
  const [creatingNewConversation, setCreatingNewConversation] = useState(false);
  const initialized = useRef(false);
  const loadingIds = useRef(new Set<string>()); // conversations whose messages are being fetched

  // Reset all conversation state when user logs out
  useEffect(() => {
    if (!isAuthenticated) {
      setConversations([]);
      setCurrentConversation(null);
      setCreatingNewConversation(false);
      initialized.current = false;
    }
  }, [isAuthenticated]);

  // Fetch existing conversations from backend on mount or after login
  useEffect(() => {
    if (initialized.current || !id || !isAuthenticated) return;
    initialized.current = true;
    fetchConversationsFromBackend();
  }, [id, isAuthenticated, user]);

  const fetchConversationsFromBackend = async () => {
    try {
      const token = getToken();
      if (!token) return;

      // 1. Get conversation list
      const listRes = await fetch(`${host}/api/conversations`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!listRes.ok) {
        // No conversations yet â€” start a fresh one
        createConversation();
        return;
      }

      const convList = await listRes.json();
      if (convList.length === 0) {
        createConversation();
        return;
      }

      // 2. The list only: each conversation's messages are fetched when it is
      // opened (loadConversation). One with no messages needs no fetch.
      const fullConversations: Conversation[] = (convList as ConversationSummary[]).map((summary) => ({
        id: summary.id,
        name: summary.name || "New Conversation",
        queries: {},
        current: "",
        timestamp: new Date(summary.created_at || new Date()),
        initialized: (summary.message_count ?? 0) > 0,
        error: false,
        loaded: (summary.message_count ?? 0) === 0,
      }));

      if (fullConversations.length > 0) {
        setConversations(fullConversations);
        // If a conversation was specified in URL, use it, otherwise select the first conversation
        const params = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
        const urlConvId = params?.get("conversation");
        const initialConv = (urlConvId && fullConversations.find(c => c.id === urlConvId)) || fullConversations[0];
        setCurrentConversation(initialConv.id);
        if (currentPage === "chat") {
          changePage("chat", { conversation: initialConv.id }, true);
        }
      } else {
        // No conversations yet â€” start a fresh empty conversation ("Ask Anything" screen)
        createConversation();
      }
    } catch (e) {
      console.error("Failed to fetch conversations:", e);
      createConversation();
    }
  };

  /**
   * Rebuild a frontend Conversation from the backend detail response.
   * Groups messages by query_id into Query objects.
   */
  const rebuildConversation = (detail: any): Conversation => {
    const queries: { [key: string]: Query } = {};
    let queryIndex = 0;

    // Group messages by query_id
    const messagesByQuery: { [key: string]: any[] } = {};
    for (const msg of detail.messages || []) {
      const qid = msg.query_id || "unknown";
      if (!messagesByQuery[qid]) {
        messagesByQuery[qid] = [];
      }
      messagesByQuery[qid].push(msg);
    }

    for (const [queryId, msgs] of Object.entries(messagesByQuery)) {
      const frontendMessages: Message[] = [];
      let queryText = "";

      for (const msg of msgs as any[]) {
        if (msg.role === "user") {
          queryText = msg.content;
          // User message
          frontendMessages.push({
            type: "User",
            id: uuidv4(),
            query_id: queryId,
            conversation_id: detail.id,
            user_id: id || "",
            payload: {
              type: "text",
              metadata: {},
              code: { language: "", title: "", text: "" },
              objects: [msg.content],
            } as ResultPayload,
          });
        } else if (msg.role === "assistant") {
          let meta: any = {};
          try {
            meta = JSON.parse(msg.metadata_json || "{}");
          } catch {}

          // If there are rows, add a product or table result message
          if (
            msg.message_type === "result" &&
            meta.success &&
            meta.rows &&
            meta.rows.length > 0
          ) {
            const columns = meta.columns || Object.keys(meta.rows[0] || {});
            const { isProduct, fieldMapping } = detectProductData(meta.rows, columns);

            if (isProduct) {
              const products = mapRowsToProducts(meta.rows, fieldMapping);
              frontendMessages.push({
                type: "result",
                id: uuidv4(),
                conversation_id: detail.id,
                user_id: id || "",
                query_id: queryId,
                payload: {
                  type: "product",
                  code: {
                    language: "sql",
                    title: "Generated SQL",
                    text: meta.generated_sql || "",
                  },
                  objects: products,
                } as ResultPayload,
              });
            } else {
              frontendMessages.push({
                type: "result",
                id: uuidv4(),
                conversation_id: detail.id,
                user_id: id || "",
                query_id: queryId,
                payload: {
                  type: "table",
                  code: {
                    language: "sql",
                    title: "Generated SQL",
                    text: meta.generated_sql || "",
                  },
                  objects: meta.rows.slice(0, 100),
                } as ResultPayload,
              });
            }
          }

          // Text response
          const statusText = meta.success
            ? msg.content
            : `âŒ ${meta.error || msg.content || "Query failed"}`;

          frontendMessages.push({
            type: "text",
            id: uuidv4(),
            conversation_id: detail.id,
            user_id: id || "",
            query_id: queryId,
            payload: {
              type: "response",
              metadata: {},
              objects: [{ text: statusText }],
            } as ResponsePayload,
          });
        }
      }

      queries[queryId] = {
        id: queryId,
        query: queryText,
        messages: frontendMessages,
        finished: true,
        query_start: new Date(
          (msgs as any[])[0]?.created_at || new Date()
        ),
        query_end: new Date(
          (msgs as any[])[(msgs as any[]).length - 1]?.created_at || new Date()
        ),
        NER: null,
        index: queryIndex++,
      };
    }

    return {
      id: detail.id,
      name: detail.name || "New Conversation",
      queries,
      current: "",
      timestamp: new Date(detail.created_at || new Date()),
      initialized: Object.keys(queries).length > 0,
      error: false,
      loaded: true,
    };
  };

  /**
   * Fetches an opened conversation's messages (once). Queries sent while the
   * fetch was running are kept, after the loaded ones. On failure the
   * conversation stays unloaded, so opening it again retries.
   */
  const loadConversation = async (conversationId: string) => {
    if (loadingIds.current.has(conversationId)) return;
    const token = getToken();
    if (!token) return;
    loadingIds.current.add(conversationId);
    try {
      const res = await fetch(`${host}/api/conversations/${conversationId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const loaded = rebuildConversation(await res.json());
      setConversations((prev) =>
        prev.map((c) => {
          if (c.id !== conversationId || c.loaded) return c;
          const offset = Object.keys(loaded.queries).length;
          const sentMeanwhile = Object.fromEntries(
            Object.entries(c.queries)
              .filter(([qid]) => !(qid in loaded.queries))
              .map(([qid, q]) => [qid, { ...q, index: offset + q.index }])
          );
          return {
            ...loaded,
            name: c.name,
            current: c.current,
            queries: { ...loaded.queries, ...sentMeanwhile },
            initialized: loaded.initialized || Object.keys(sentMeanwhile).length > 0,
          };
        })
      );
    } catch (e) {
      console.error("Failed to load conversation:", e);
    } finally {
      loadingIds.current.delete(conversationId);
    }
  };

  // Load the open conversation's messages when it hasn't been loaded yet
  // (first open after login, selecting it in the sidebar, the URL, ...).
  const openConversation = conversations.find((c) => c.id === currentConversation);
  const openId = openConversation?.id;
  const openLoaded = openConversation?.loaded;
  useEffect(() => {
    if (openId && openLoaded === false) loadConversation(openId);
    // loadConversation is recreated each render; it guards repeat calls itself
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openId, openLoaded]);

  // Used by the "New Chat" / "+" buttons: opens a conversation that has no
  // messages yet if there is one, instead of adding another.
  // openChat also switches to the chat page when on another page.
  const startNewConversation = (openChat: boolean = false) => {
    const empty = conversations.find(
      (c) => c.loaded && Object.keys(c.queries).length === 0
    );
    if (!empty) {
      createConversation(openChat);
      return;
    }
    setCurrentConversation(empty.id);
    if (openChat || currentPage === "chat") {
      changePage("chat", { conversation: empty.id }, true);
    }
  };

  const createConversation = (openChat: boolean = false) => {
    if (creatingNewConversation) return;
    setCreatingNewConversation(true);
    const conversation_id = uuidv4();

    // Only create locally â€” backend creation is deferred until the first message is sent
    const newConversation: Conversation = {
      ...initialConversation,
      id: conversation_id,
      timestamp: new Date(),
    };
    setConversations((prev) => [...prev, newConversation]);
    setCurrentConversation(conversation_id);
    setCreatingNewConversation(false);
    if (openChat || currentPage === "chat") {
      changePage("chat", { conversation: conversation_id }, true);
    }
  };

  // Removes conversations from the UI only. If the open conversation goes,
  // select the one below it in the sidebar (newest first), or the one above
  // if it was last.
  const dropConversations = (ids: string[]) => {
    const gone = new Set(ids);
    if (!conversations.some((c) => gone.has(c.id))) return;
    const ordered = [...conversations].sort(
      (a, b) =>
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );
    const index = ordered.findIndex((c) => c.id === currentConversation);
    const remaining = ordered.filter((c) => !gone.has(c.id));

    setConversations((prev) => prev.filter((c) => !gone.has(c.id)));
    if (remaining.length === 0) {
      createConversation();
    } else if (currentConversation && gone.has(currentConversation)) {
      const next = remaining[Math.min(index, remaining.length - 1)];
      setCurrentConversation(next.id);
      if (currentPage === "chat") {
        changePage("chat", { conversation: next.id }, true);
      }
    }
  };

  const removeConversation = async (conversation_id: string) => {
    dropConversations([conversation_id]);

    // Delete on backend
    try {
      const token = getToken();
      if (token) {
        await fetch(`${host}/api/conversations/${conversation_id}`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        });
      }
    } catch (e) {
      console.error("Failed to delete conversation on backend:", e);
    }
  };

  const selectConversation = (id: string) => {
    setCurrentConversation(id);
    changePage("chat", { conversation: id }, true);
  };

  const setConversationStatus = (status: string, conversationId: string) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id === conversationId ? { ...c, current: status } : c
      )
    );
  };

  const setConversationTitle = async (title: string, conversationId: string) => {
    // Update on backend
    try {
      const token = getToken();
      if (token) {
        await fetch(`${host}/api/conversations/${conversationId}`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ name: title }),
        });
      }
    } catch (e) {
      console.error("Failed to update conversation title:", e);
    }

    setConversations((prev) =>
      prev.map((c) =>
        c.id === conversationId ? { ...c, name: title } : c
      )
    );
  };

  const addMessageToConversation = (
    messages: Message[],
    conversationId: string,
    queryId: string
  ) => {
    setConversations((prev) =>
      prev.map((c) => {
        if (c.id === conversationId && c.queries[queryId]) {
          return {
            ...c,
            initialized: true,
            queries: {
              ...c.queries,
              [queryId]: {
                ...c.queries[queryId],
                messages: [...c.queries[queryId].messages, ...messages],
              },
            },
          };
        }
        return c;
      })
    );
  };

  const addQueryToConversation = async (
    conversationId: string,
    query: string,
    query_id: string
  ) => {
    // Lazily create conversation on backend when first message is sent
    const conversation = conversations.find((c) => c.id === conversationId);
    if (conversation && Object.keys(conversation.queries).length === 0) {
      try {
        const token = getToken();
        if (token) {
          await fetch(`${host}/api/conversations`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ id: conversationId, name: "New Conversation" }),
          });
        }
      } catch (e) {
        console.error("Failed to create conversation on backend:", e);
      }
    }

    const userMessage: Message = {
      type: "User",
      id: uuidv4(),
      query_id,
      conversation_id: conversationId,
      user_id: id || "",
      payload: {
        type: "text",
        metadata: {},
        code: { language: "", title: "", text: "" },
        objects: [query],
      },
    };

    const newQuery: Query = {
      id: query_id,
      query,
      finished: false,
      query_start: new Date(),
      query_end: null,
      NER: null,
      index: 0,
      messages: [userMessage],
    };

    // Next index after the existing queries, so the new query sorts last
    // (loaded conversations already use indexes 0..n-1).
    setConversations((prev) =>
      prev.map((c) => {
        if (c.id !== conversationId) return c;
        const nextIndex =
          Math.max(-1, ...Object.values(c.queries).map((q) => q.index)) + 1;
        return {
          ...c,
          queries: { ...c.queries, [query_id]: { ...newQuery, index: nextIndex } },
        };
      })
    );
  };

  const finishQuery = (conversationId: string, queryId: string) => {
    setConversations((prev) =>
      prev.map((c) => {
        if (c.id === conversationId && c.queries[queryId]) {
          return {
            ...c,
            queries: {
              ...c.queries,
              [queryId]: {
                ...c.queries[queryId],
                finished: true,
                query_end: new Date(),
              },
            },
          };
        }
        return c;
      })
    );
  };

  const addSuggestionToConversation = async (
    conversationId: string,
    queryId: string,
    connectionId?: number | null,
    knowledgeBaseId?: number | null
  ) => {
    try {
      const token = getToken();
      if (!token || !connectionId) return;

      // Build conversation history from the current conversation's queries
      const conversation = conversations.find((c) => c.id === conversationId);
      const conversationHistory: { role: string; content: string }[] = [];
      if (conversation) {
        const sortedQueries = Object.values(conversation.queries)
          .sort((a, b) => a.index - b.index)
          .slice(-5);
        for (const q of sortedQueries) {
          if (q.query) {
            conversationHistory.push({ role: "user", content: q.query });
          }
          // Find assistant text responses in messages
          for (const msg of q.messages) {
            if (
              msg.type === "text" &&
              msg.payload &&
              "objects" in msg.payload &&
              Array.isArray(msg.payload.objects) &&
              msg.payload.objects.length > 0
            ) {
              const textObj = msg.payload.objects[0] as any;
              if (textObj?.text) {
                conversationHistory.push({
                  role: "assistant",
                  content: textObj.text,
                });
              }
            }
          }
        }
      }

      const response = await fetch(`${host}/api/suggestions/conversation`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          connection_id: connectionId,
          knowledge_base_id: knowledgeBaseId || null,
          conversation_history: conversationHistory,
        }),
      });

      let suggestions = [
        "Show me more details about the results",
        "What are the top records by count?",
        "Are there any related tables to explore?",
      ];

      if (response.ok) {
        const data = await response.json();
        if (data.suggestions && data.suggestions.length > 0) {
          suggestions = data.suggestions;
        }
      }

      const newMessage: Message = {
        type: "suggestion",
        id: uuidv4(),
        conversation_id: conversationId,
        query_id: queryId,
        user_id: id || "",
        payload: {
          error: "",
          suggestions,
        },
      };
      addMessageToConversation([newMessage], conversationId, queryId);
    } catch {
      // Silently fail for suggestions
    }
  };



  return (
    <ConversationContext.Provider
      value={{
        conversations,
        currentConversation,
        creatingNewConversation,
        startNewConversation,
        removeConversation,
        dropConversations,
        selectConversation,
        setConversationStatus,
        setConversationTitle,
        addMessageToConversation,
        addQueryToConversation,
        finishQuery,
        addSuggestionToConversation,
      }}
    >
      {children}
    </ConversationContext.Provider>
  );
};
