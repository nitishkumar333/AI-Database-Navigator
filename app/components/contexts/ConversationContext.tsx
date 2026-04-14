"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Conversation, initialConversation } from "../types";
import {
  Query,
  Message,
  TextPayload,
  SuggestionPayload,
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
    queryId: string
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
  const { getToken } = useContext(AuthContext);

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversation, setCurrentConversation] = useState<string | null>(
    null
  );
  const [creatingNewConversation, setCreatingNewConversation] = useState(false);
  const initialized = useRef(false);

  // Auto-create a first conversation on mount
  useEffect(() => {
    if (initialized.current || !id) return;
    initialized.current = true;
    startNewConversation();
  }, [id]);

  const startNewConversation = () => {
    if (creatingNewConversation) return;
    setCreatingNewConversation(true);
    const conversation_id = uuidv4();
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

  const removeConversation = (conversation_id: string) => {
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

  const setConversationTitle = (title: string, conversationId: string) => {
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

  const addQueryToConversation = (
    conversationId: string,
    query: string,
    query_id: string
  ) => {
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
    queryId: string
  ) => {
    try {
      const token = getToken();
      const response = await fetch(`${host}/api/connections`, {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
      if (!response.ok) return;
      const connections = await response.json();
      if (connections.length === 0) return;

      // Generate simple suggestions based on connection
      const suggestions = [
        "Show me all tables in the database",
        "What are the most recent records?",
        "How many rows are in each table?",
      ];

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

  // Auto-select conversation from URL
  useEffect(() => {
    if (conversations.length > 0 && !currentConversation) {
      const latest = conversations[conversations.length - 1];
      setCurrentConversation(latest.id);
    }
  }, [conversations, currentConversation]);

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
