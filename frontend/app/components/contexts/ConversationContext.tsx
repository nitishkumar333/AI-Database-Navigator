"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Conversation, Query, Message, ResultPayload } from "@/app/types/chat";
import { v4 as uuidv4 } from "uuid";
import { RouterContext } from "./RouterContext";
import { AuthContext } from "./AuthContext";
import { apiFetch } from "../../utils/api";
import { buildResultPayload, textMessage } from "@/app/utils/resultMessages";

// One entry of GET /api/conversations.
type ConversationSummary = {
  id: string;
  name?: string;
  created_at?: string | null;
  message_count?: number;
};

// GET /api/conversations/{id}.
type ConversationDetail = {
  id: string;
  name?: string;
  created_at?: string | null;
  messages?: StoredMessage[];
};

type StoredMessage = {
  role: "user" | "assistant";
  content: string;
  query_id?: string | null;
  message_type?: string;
  metadata_json?: string | null;
};

type StoredMetadata = {
  success?: boolean;
  error?: string;
  rows?: Record<string, unknown>[];
  columns?: string[];
  generated_sql?: string;
};

const FALLBACK_SUGGESTIONS = [
  "Show me more details about the results",
  "What are the top records by count?",
  "Are there any related tables to explore?",
];

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

const newestFirst = (a: Conversation, b: Conversation) =>
  new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();

const userMessage = (
  conversationId: string,
  queryId: string,
  text: string
): Message => ({
  type: "User",
  id: uuidv4(),
  query_id: queryId,
  conversation_id: conversationId,
  payload: {
    type: "text",
    code: { language: "", title: "", text: "" },
    objects: [text],
  } as ResultPayload,
});

/**
 * Rebuild a frontend Conversation from the backend detail response.
 * Groups messages by query_id into Query objects.
 */
const rebuildConversation = (detail: ConversationDetail): Conversation => {
  const queries: { [key: string]: Query } = {};

  // Group messages by query_id
  const messagesByQuery: { [key: string]: StoredMessage[] } = {};
  for (const msg of detail.messages || []) {
    const qid = msg.query_id || "unknown";
    (messagesByQuery[qid] ||= []).push(msg);
  }

  Object.entries(messagesByQuery).forEach(([queryId, msgs], queryIndex) => {
    const frontendMessages: Message[] = [];
    let queryText = "";

    for (const msg of msgs) {
      if (msg.role === "user") {
        queryText = msg.content;
        frontendMessages.push(userMessage(detail.id, queryId, msg.content));
      } else if (msg.role === "assistant") {
        let meta: StoredMetadata = {};
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
          frontendMessages.push({
            type: "result",
            id: uuidv4(),
            conversation_id: detail.id,
            query_id: queryId,
            payload: buildResultPayload(meta.rows, columns, meta.generated_sql, {
              table: 100,
            }),
          });
        }

        // Text response
        const statusText = meta.success
          ? msg.content
          : `❌ ${meta.error || msg.content || "Query failed"}`;
        frontendMessages.push(textMessage(detail.id, queryId, statusText));
      }
    }

    queries[queryId] = {
      id: queryId,
      query: queryText,
      messages: frontendMessages,
      finished: true,
      index: queryIndex,
    };
  });

  return {
    id: detail.id,
    name: detail.name || "New Conversation",
    queries,
    current: "",
    timestamp: new Date(detail.created_at || new Date()),
    loaded: true,
  };
};

export const ConversationProvider = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  const { changePage, currentPage } = useContext(RouterContext);
  const { isAuthenticated } = useContext(AuthContext);

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

  // Fetch existing conversations from backend after login
  useEffect(() => {
    if (initialized.current || !isAuthenticated) return;
    initialized.current = true;
    fetchConversationsFromBackend();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  const fetchConversationsFromBackend = async () => {
    try {
      const listRes = await apiFetch("/api/conversations");
      const convList: ConversationSummary[] = listRes.ok ? await listRes.json() : [];
      if (convList.length === 0) {
        // No conversations yet — start a fresh empty one ("Ask Anything" screen)
        createConversation();
        return;
      }

      // The list only: each conversation's messages are fetched when it is
      // opened (loadConversation). One with no messages needs no fetch.
      const fullConversations: Conversation[] = convList.map((summary) => ({
        id: summary.id,
        name: summary.name || "New Conversation",
        queries: {},
        current: "",
        timestamp: new Date(summary.created_at || new Date()),
        loaded: (summary.message_count ?? 0) === 0,
      }));

      setConversations(fullConversations);
      // If a conversation was specified in URL, use it, otherwise select the first conversation
      const urlConvId = new URLSearchParams(window.location.search).get("conversation");
      const initialConv =
        (urlConvId && fullConversations.find((c) => c.id === urlConvId)) ||
        fullConversations[0];
      setCurrentConversation(initialConv.id);
      if (currentPage === "chat") {
        changePage("chat", { conversation: initialConv.id }, true);
      }
    } catch (e) {
      console.error("Failed to fetch conversations:", e);
      createConversation();
    }
  };

  /**
   * Fetches an opened conversation's messages (once). Queries sent while the
   * fetch was running are kept, after the loaded ones. On failure the
   * conversation stays unloaded, so opening it again retries.
   */
  const loadConversation = async (conversationId: string) => {
    if (loadingIds.current.has(conversationId)) return;
    loadingIds.current.add(conversationId);
    try {
      const res = await apiFetch(`/api/conversations/${conversationId}`);
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

  // Used by the "New Chat" / "+" buttons: opens the newest conversation that
  // has no messages yet if there is one, instead of adding another.
  // openChat also switches to the chat page when on another page.
  const startNewConversation = (openChat: boolean = false) => {
    const empty = [...conversations]
      .sort(newestFirst)
      .find((c) => c.loaded && Object.keys(c.queries).length === 0);
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

    // Only create locally — backend creation is deferred until the first message is sent
    const newConversation: Conversation = {
      id: conversation_id,
      name: "New Conversation",
      queries: {},
      current: "",
      timestamp: new Date(),
      loaded: true,
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
    const ordered = [...conversations].sort(newestFirst);
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
    try {
      await apiFetch(`/api/conversations/${conversation_id}`, { method: "DELETE" });
    } catch (e) {
      console.error("Failed to delete conversation on backend:", e);
    }
  };

  const selectConversation = (id: string) => {
    setCurrentConversation(id);
    changePage("chat", { conversation: id }, true);
  };

  const updateConversation = (
    conversationId: string,
    update: (c: Conversation) => Conversation
  ) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === conversationId ? update(c) : c))
    );
  };

  // Applies `update` to a query of a conversation, if both exist.
  const updateQuery = (
    conversationId: string,
    queryId: string,
    update: (q: Query) => Query
  ) => {
    updateConversation(conversationId, (c) =>
      c.queries[queryId]
        ? { ...c, queries: { ...c.queries, [queryId]: update(c.queries[queryId]) } }
        : c
    );
  };

  const setConversationStatus = (status: string, conversationId: string) => {
    updateConversation(conversationId, (c) => ({ ...c, current: status }));
  };

  const setConversationTitle = async (title: string, conversationId: string) => {
    try {
      await apiFetch(`/api/conversations/${conversationId}`, {
        method: "PUT",
        body: { name: title },
      });
    } catch (e) {
      console.error("Failed to update conversation title:", e);
    }
    updateConversation(conversationId, (c) => ({ ...c, name: title }));
  };

  const addMessageToConversation = (
    messages: Message[],
    conversationId: string,
    queryId: string
  ) => {
    updateQuery(conversationId, queryId, (q) => ({
      ...q,
      messages: [...q.messages, ...messages],
    }));
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
        await apiFetch("/api/conversations", {
          method: "POST",
          body: { id: conversationId, name: "New Conversation" },
        });
      } catch (e) {
        console.error("Failed to create conversation on backend:", e);
      }
    }

    // Next index after the existing queries, so the new query sorts last
    // (loaded conversations already use indexes 0..n-1).
    updateConversation(conversationId, (c) => {
      const nextIndex =
        Math.max(-1, ...Object.values(c.queries).map((q) => q.index)) + 1;
      const newQuery: Query = {
        id: query_id,
        query,
        finished: false,
        index: nextIndex,
        messages: [userMessage(conversationId, query_id, query)],
      };
      return { ...c, queries: { ...c.queries, [query_id]: newQuery } };
    });
  };

  const finishQuery = (conversationId: string, queryId: string) => {
    updateQuery(conversationId, queryId, (q) => ({ ...q, finished: true }));
  };

  const addSuggestionToConversation = async (
    conversationId: string,
    queryId: string,
    connectionId?: number | null,
    knowledgeBaseId?: number | null
  ) => {
    try {
      if (!connectionId) return;

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
            if (msg.type !== "text" || !("objects" in msg.payload)) continue;
            const text = (msg.payload.objects[0] as { text?: string } | undefined)?.text;
            if (text) {
              conversationHistory.push({ role: "assistant", content: text });
            }
          }
        }
      }

      const response = await apiFetch("/api/suggestions/conversation", {
        method: "POST",
        body: {
          connection_id: connectionId,
          knowledge_base_id: knowledgeBaseId || null,
          conversation_history: conversationHistory,
        },
      });

      let suggestions = FALLBACK_SUGGESTIONS;
      if (response.ok) {
        const data = await response.json();
        if (data.suggestions && data.suggestions.length > 0) {
          suggestions = data.suggestions;
        }
      }

      addMessageToConversation(
        [
          {
            type: "suggestion",
            id: uuidv4(),
            conversation_id: conversationId,
            query_id: queryId,
            payload: { error: "", suggestions },
          },
        ],
        conversationId,
        queryId
      );
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
