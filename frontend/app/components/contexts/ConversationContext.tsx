"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Conversation, initialConversation } from "../types";
import {
  Query,
  Message,
  TextPayload,
  SuggestionPayload,
  ResultPayload,
  ResponsePayload,
} from "@/app/types/chat";
import { v4 as uuidv4 } from "uuid";
import { SessionContext } from "./SessionContext";
import { RouterContext } from "./RouterContext";
import { AuthContext } from "./AuthContext";
import { host } from "../host";
import { QueryContext } from "./SocketContext";

export const ConversationContext = createContext<{
  conversations: Conversation[];
  currentConversation: string | null;
  setCurrentConversation: (id: string | null) => void;
  creatingNewConversation: boolean;
  startNewConversation: () => void;
  removeConversation: (id: string) => void;
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
  handleConversationError: (conversationId: string) => void;
  addSuggestionToConversation: (
    conversationId: string,
    queryId: string,
    connectionId?: number | null,
    knowledgeBaseId?: number | null
  ) => void;
}>({
  conversations: [],
  currentConversation: null,
  setCurrentConversation: () => {},
  creatingNewConversation: false,
  startNewConversation: () => {},
  removeConversation: () => {},
  selectConversation: () => {},
  setConversationStatus: () => {},
  setConversationTitle: () => {},
  addMessageToConversation: () => {},
  addQueryToConversation: () => {},
  finishQuery: () => {},
  handleConversationError: () => {},
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
        // No conversations yet — start a fresh one
        startNewConversation();
        return;
      }

      const convList = await listRes.json();
      if (convList.length === 0) {
        startNewConversation();
        return;
      }

      // 2. Fetch full details (with messages) for each conversation
      const fullConversations: Conversation[] = [];
      for (const convSummary of convList) {
        const detailRes = await fetch(
          `${host}/api/conversations/${convSummary.id}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (!detailRes.ok) continue;
        const detail = await detailRes.json();

        // Rebuild the frontend Conversation object from backend data
        const conv = rebuildConversation(detail);
        fullConversations.push(conv);
      }

      if (fullConversations.length > 0) {
        setConversations(fullConversations);
      }
      // Always start with a fresh empty conversation ("Ask Anything" screen)
      startNewConversation();
    } catch (e) {
      console.error("Failed to fetch conversations:", e);
      startNewConversation();
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

          // If there are rows, add a table result message
          if (
            msg.message_type === "result" &&
            meta.success &&
            meta.rows &&
            meta.rows.length > 0
          ) {
            frontendMessages.push({
              type: "result",
              id: uuidv4(),
              conversation_id: detail.id,
              user_id: id || "",
              query_id: queryId,
              payload: {
                type: "table",
                metadata: {
                  row_count: meta.row_count || 0,
                  latency_ms: meta.latency_ms || 0,
                },
                code: {
                  language: "sql",
                  title: "Generated SQL",
                  text: meta.generated_sql || "",
                },
                objects: meta.rows.slice(0, 100),
              } as ResultPayload,
            });
          }

          // Text response
          const statusText = meta.success
            ? msg.content
            : `❌ ${meta.error || msg.content || "Query failed"}`;

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
        feedback: null,
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
    };
  };

  const startNewConversation = async () => {
    if (creatingNewConversation) return;
    setCreatingNewConversation(true);
    const conversation_id = uuidv4();

    // Only create locally — backend creation is deferred until the first message is sent
    const newConversation: Conversation = {
      ...initialConversation,
      id: conversation_id,
      timestamp: new Date(),
    };
    setConversations((prev) => [...prev, newConversation]);
    setCurrentConversation(conversation_id);
    setCreatingNewConversation(false);
    if (currentPage === "chat") {
      changePage("chat", { conversation: conversation_id }, true);
    }
  };

  const removeConversation = async (conversation_id: string) => {
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

    setConversations((prev) => prev.filter((c) => c.id !== conversation_id));
    if (currentConversation === conversation_id) {
      setCurrentConversation(null);
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
      feedback: null,
      NER: null,
      index: 0,
      messages: [userMessage],
    };

    setConversations((prev) =>
      prev.map((c) =>
        c.id === conversationId
          ? { ...c, queries: { ...c.queries, [query_id]: newQuery } }
          : c
      )
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

  const handleConversationError = (conversationId: string) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id === conversationId ? { ...c, error: true } : c
      )
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
        setCurrentConversation,
        creatingNewConversation,
        startNewConversation,
        removeConversation,
        selectConversation,
        setConversationStatus,
        setConversationTitle,
        addMessageToConversation,
        addQueryToConversation,
        finishQuery,
        handleConversationError,
        addSuggestionToConversation,
      }}
    >
      {children}
    </ConversationContext.Provider>
  );
};
