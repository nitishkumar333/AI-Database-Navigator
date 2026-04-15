"use client";

import React, { useEffect, useState, useRef, useContext } from "react";
import { motion } from "framer-motion";

import { Query, Message, ResultPayload, ResponsePayload } from "@/app/types/chat";
import { MdChatBubbleOutline } from "react-icons/md";

import QueryInput from "../components/chat/QueryInput";
import RenderChat from "../components/chat/RenderChat";
import CollectionSelection from "../components/chat/components/CollectionSelection";
import KnowledgeBaseSelection from "../components/chat/components/KnowledgeBaseSelection";
import { QueryContext } from "../components/contexts/SocketContext";
import { SessionContext } from "../components/contexts/SessionContext";
import { ConversationContext } from "../components/contexts/ConversationContext";
import { ChatProvider } from "../components/contexts/ChatContext";
import { v4 as uuidv4 } from "uuid";
import { IoRefresh } from "react-icons/io5";

import { Button } from "@/components/ui/button";

// import dynamic from "next/dynamic";
import { Separator } from "@/components/ui/separator";
import { CollectionContext } from "../components/contexts/CollectionContext";

// const AbstractSphereScene = dynamic(
//   () => import("@/app/components/threejs/AbstractSphere"),
//   {
//     ssr: false,
//   }
// );

interface KnowledgeBaseEntry {
  id: number;
  connection_id: number;
  table_name: string;
  table_description: string;
}
export default function ChatPage() {
  const { sendQuery } = useContext(QueryContext);
  const { id } = useContext(SessionContext);
  const {
    addQueryToConversation,
    addMessageToConversation,
    setConversationStatus,
    setConversationTitle,
    finishQuery,
    addSuggestionToConversation,
    currentConversation,
    conversations,
  } = useContext(ConversationContext);

  const { getRandomPrompts, collections, connections } = useContext(CollectionContext);

  // Connection & KB selection state
  const [selectedConnectionId, setSelectedConnectionId] = useState<number | null>(null);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<number | null>(null);

  const [currentQuery, setCurrentQuery] = useState<{
    [key: string]: Query;
  }>({});
  const [currentTitle, setCurrentTitle] = useState<string>("");
  const [currentStatus, setCurrentStatus] = useState<string>("");

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const displacementStrength = useRef(0.0);
  const distortionStrength = useRef(0.0);

  const addDisplacement = (value: number) => {
    displacementStrength.current += value;
    displacementStrength.current = Math.min(displacementStrength.current, 0.1);
  };

  const addDistortion = (value: number) => {
    distortionStrength.current += value;
    distortionStrength.current = Math.min(distortionStrength.current, 0.3);
  };

  const [randomPrompts, setRandomPrompts] = useState<string[]>([]);

  const handleSendQuery = async (query: string) => {
    if (query.trim() === "" || currentStatus !== "") return;
    const trimmedQuery = query.trim();
    const query_id = uuidv4();

    const conversation = conversations.find(
      (c) => c.id === currentConversation
    );
    if (!conversation) return;

    // Add user query to conversation
    addQueryToConversation(conversation.id, trimmedQuery, query_id);
    setConversationStatus("Thinking...", conversation.id);

    // Send via REST API — now passing connection_id and knowledge_base_id
    const result = await sendQuery(trimmedQuery, selectedConnectionId, selectedKnowledgeBaseId);

    if (!result) {
      setConversationStatus("", conversation.id);
      finishQuery(conversation.id, query_id);
      return;
    }

    // Build response messages
    const messages: Message[] = [];

    // If there are rows to display, add a table result
    if (result.success && result.rows && result.rows.length > 0) {
      const tableMessage: Message = {
        type: "result",
        id: uuidv4(),
        conversation_id: conversation.id,
        user_id: id || "",
        query_id: query_id,
        payload: {
          type: "table",
          metadata: {
            row_count: result.row_count || 0,
            latency_ms: result.latency_ms || 0,
          },
          code: {
            language: "sql",
            title: "Generated SQL",
            text: result.generated_sql || "",
          },
          objects: result.rows.slice(0, 100) as { [key: string]: string }[],
        } as ResultPayload,
      };
      messages.push(tableMessage);
    }

    // Add text response (summary/status)
    const statusText = result.success
      ? result.response_text
      : `❌ ${result.error || "Query failed"}`;
    
    const textMessage: Message = {
      type: "text",
      id: uuidv4(),
      conversation_id: conversation.id,
      user_id: id || "",
      query_id: query_id,
      payload: {
        type: "response",
        metadata: {},
        objects: [{ text: statusText }],
      } as ResponsePayload,
    };
    messages.push(textMessage);

    addMessageToConversation(messages, conversation.id, query_id);

    // Set title from first query
    if (Object.keys(conversation.queries).length === 0) {
      const title =
        trimmedQuery.substring(0, 40) +
        (trimmedQuery.length > 40 ? "..." : "");
      setConversationTitle(title, conversation.id);
    }

    setConversationStatus("", conversation.id);
    finishQuery(conversation.id, query_id);
    addSuggestionToConversation(conversation.id, query_id);
  };

  useEffect(() => {
    setCurrentQuery(
      currentConversation && conversations.length > 0
        ? conversations.find((c) => c.id === currentConversation)?.queries || {}
        : {}
    );
    setCurrentStatus(
      currentConversation && conversations.length > 0
        ? conversations.find((c) => c.id === currentConversation)?.current || ""
        : ""
    );
    setCurrentTitle(
      currentConversation && conversations.length > 0
        ? conversations.find((c) => c.id === currentConversation)?.name || ""
        : ""
    );
  }, [currentConversation, conversations]);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }
  }, [currentQuery, currentStatus]);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView();
    }
  }, []);

  useEffect(() => {
    if (collections.length > 0) {
      setRandomPrompts(getRandomPrompts(4));
    }
  }, [collections]);

  // Auto-select first connection if none selected
  useEffect(() => {
    if (!selectedConnectionId && connections.length > 0) {
      setSelectedConnectionId(connections[0].id);
    }
  }, [connections]);

  return (
    <div className="flex flex-col w-full h-full items-center justify-start gap-3">
      <div className="flex w-full justify-between items-center lg:sticky z-20 top-0 lg:p-0 p-4 gap-5 bg-background border-b border-foreground/5 pb-2">
        <div className="flex gap-2 items-center justify-center fade-in">
          <p className="text-primary text-sm font-medium opacity-80">
            {currentTitle && currentTitle != "New Conversation"
              ? currentTitle
              : "New Conversation"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <CollectionSelection
            selectedConnectionId={selectedConnectionId}
            onConnectionChange={(connId) => {
              setSelectedConnectionId(connId);
              if (connId !== selectedConnectionId) {
                setSelectedKnowledgeBaseId(null);
              }
            }}
          />
          <KnowledgeBaseSelection
            selectedConnectionId={selectedConnectionId}
            selectedKnowledgeBaseId={selectedKnowledgeBaseId}
            onKnowledgeBaseChange={setSelectedKnowledgeBaseId}
          />
        </div>
      </div>
      {currentConversation != null && <Separator className="w-full hidden" />}

      <div className="flex flex-col w-full max-h-[calc(100vh-120px)] overflow-y-auto justify-center items-center">
        <div className="flex flex-col w-full md:w-[60vw] lg:w-[40vw] h-[80vh]">
          {currentQuery &&
            Object.entries(currentQuery)
              .sort((a, b) => a[1].index - b[1].index)
              .map(([queryId, query], index, array) => (
                <ChatProvider key={queryId}>
                  <RenderChat
                    key={queryId + index}
                    messages={query.messages}
                    conversationID={currentConversation || ""}
                    queryID={queryId}
                    finished={query.finished}
                    query_start={query.query_start}
                    query_end={query.query_end}
                    _collapsed={index !== array.length - 1}
                    messagesEndRef={messagesEndRef}
                    NER={query.NER}
                    feedback={query.feedback}
                    updateFeedback={() => {}}
                    addDisplacement={addDisplacement}
                    addDistortion={addDistortion}
                    handleSendQuery={handleSendQuery}
                    isLastQuery={index === array.length - 1}
                  />
                </ChatProvider>
              ))}
          {currentQuery && !(Object.keys(currentQuery).length === 0) && (
            <div>
              <hr className="w-full border-t border-transparent my-4 mb-20" />
            </div>
          )}
        </div>
        <div className="w-full justify-center items-center flex z-10">
          <QueryInput
            query_length={Object.keys(currentQuery).length}
            currentStatus={currentStatus}
            handleSendQuery={handleSendQuery}
            addDisplacement={addDisplacement}
            addDistortion={addDistortion}
            selectSettings={() => {}}
            selectedConnectionId={selectedConnectionId}
            onConnectionChange={(connId) => {
              setSelectedConnectionId(connId);
              if (connId !== selectedConnectionId) {
                setSelectedKnowledgeBaseId(null);
              }
            }}
            selectedKnowledgeBaseId={selectedKnowledgeBaseId}
            onKnowledgeBaseChange={setSelectedKnowledgeBaseId}
          />
        </div>
        {Object.keys(currentQuery).length === 0 && (
          <div
            className={`absolute flex pointer-events-none -z-30 items-center justify-center lg:w-fit lg:h-fit w-full h-full fade-in`}
          >
            <div
              className={`cursor-pointer lg:w-[35vw] lg:h-[35vw] w-[90vw] h-[90vw]  `}
            >
              {/* <AbstractSphereScene
                debug={false}
                displacementStrength={displacementStrength}
                distortionStrength={distortionStrength}
              /> */}
            </div>
          </div>
        )}
        {Object.keys(currentQuery).length === 0 && (
          <div className="absolute flex flex-col justify-center items-center w-full h-full gap-3 fade-in">
            <div className="flex items-center gap-4">
              <p className="text-primary text-3xl font-semibold">
                Ask AI Data Analyst
              </p>
              <Button
                variant="default"
                className="w-10"
                onClick={() => {
                  setRandomPrompts(getRandomPrompts(4));
                }}
              >
                <IoRefresh />
              </Button>
            </div>

            <motion.div
              className="flex flex-col w-full md:w-[60vw] lg:w-[40vw] gap-3"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{
                staggerChildren: 0.03,
                delayChildren: 0.05,
              }}
            >
              {randomPrompts.map((prompt, index) => (
                <motion.button
                  key={index + "prompt"}
                  onClick={() => handleSendQuery(prompt)}
                  className="whitespace-normal px-4 pt-2 text-left h-auto hover:bg-foreground text-sm rounded-lg transition-all duration-200 ease-in-out flex flex-col items-start justify-start overflow-hidden relative group"
                  initial={{ opacity: 0, y: 20, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{
                    duration: 0.2,
                    delay: index * 0.03,
                    ease: "easeOut",
                  }}
                  whileHover={{
                    scale: 1.02,
                    y: -2,
                    transition: { duration: 0.1 },
                  }}
                  whileTap={{
                    scale: 0.98,
                    y: 0,
                  }}
                >
                  <div className="flex items-center justify-start gap-2 relative z-10">
                    <motion.div
                      whileHover={{
                        scale: 1.1,
                        rotate: [0, -10, 10, -5, 5, 0],
                        transition: {
                          duration: 0.5,
                          ease: "easeInOut",
                          times: [0, 0.2, 0.4, 0.6, 0.8, 1],
                        },
                      }}
                    >
                      <MdChatBubbleOutline size={14} />
                    </motion.div>
                    <motion.p
                      className="text-primary text-sm truncate lg:w-[35vw] w-[80vw]"
                      initial={{ opacity: 0.8 }}
                      whileHover={{
                        opacity: 1,
                        transition: { duration: 0.2 },
                      }}
                    >
                      {prompt}
                    </motion.p>
                  </div>
                  <motion.div
                    className="border-b border-foreground w-full pt-2 origin-left"
                    initial={{ scaleX: 0, opacity: 0.3 }}
                    whileHover={{
                      scaleX: 1,
                      opacity: 1,
                      transition: { duration: 0.3, ease: "easeOut" },
                    }}
                  />
                  <motion.div
                    className="absolute inset-0 bg-gradient-to-r from-primary/5 to-primary/10 rounded-lg opacity-0"
                    whileHover={{
                      opacity: 1,
                      transition: { duration: 0.3 },
                    }}
                  />
                </motion.button>
              ))}
            </motion.div>
          </div>
        )}
      </div>
    </div>
  );
}
