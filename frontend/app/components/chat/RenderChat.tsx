"use client";

import React, { useContext, useEffect, useMemo, useState } from "react";

import {
  Message,
  ResponsePayload,
  ResultPayload,
  SuggestionPayload,
  UserPayload,
} from "@/app/types/chat";

import UserMessageDisplay from "./displays/SystemMessages/UserMessageDisplay";
import TextDisplay from "./displays/Generic/TextDisplay";
import { Skeleton } from "@/components/ui/skeleton";
import { QueryContext } from "../contexts/QueryContext";
import SuggestionDisplay from "./displays/SystemMessages/SuggestionDisplay";
import CodeView from "./displays/QueryCode/CodeView";
import ResultView from "./displays/Result/ResultView";

interface RenderChatProps {
  messages: Message[];
  _collapsed: boolean;
  messagesEndRef: React.RefObject<HTMLDivElement>;
  finished: boolean;
  handleSendQuery: (query: string) => void;
  isLastQuery: boolean;
}

const ResultItemDisplay: React.FC<{ payload: ResultPayload }> = ({ payload }) => {
  const [showCode, setShowCode] = useState(true);

  return (
    <div className="w-full flex flex-col justify-start items-start gap-3">
      {showCode && (
        <div className="w-full mt-2">
          <CodeView code={payload.code} onClose={() => setShowCode(false)} />
        </div>
      )}
      <ResultView result={payload.result} />
    </div>
  );
};

const RenderChat: React.FC<RenderChatProps> = ({
  messages,
  _collapsed,
  messagesEndRef,
  finished,
  handleSendQuery,
  isLastQuery,
}) => {
  const [collapsed, setCollapsed] = useState<boolean>(_collapsed);
  const { backendOnline } = useContext(QueryContext);

  const messagesTopRef = React.useRef<HTMLDivElement>(null);

  // Scroll to this question when its messages change. Deferred a frame so it
  // runs after ChatPage's scroll to the end of the chat and wins over it.
  useEffect(() => {
    if (messages.length === 0) return;
    const frame = requestAnimationFrame(() =>
      messagesTopRef.current?.scrollIntoView({ behavior: "smooth" })
    );
    return () => cancelAnimationFrame(frame);
  }, [messages.length]);

  // Results and text responses, with consecutive text responses merged into one.
  const outputItems = useMemo(() => {
    const output: Message[] = [];
    for (const message of messages) {
      if (message.type === "User" || message.type === "suggestion") continue;
      const last = output[output.length - 1];
      if (message.type === "text" && last?.type === "text") {
        output[output.length - 1] = {
          ...last,
          payload: {
            type: "response",
            objects: [
              ...(last.payload as ResponsePayload).objects,
              ...(message.payload as ResponsePayload).objects,
            ],
          },
        };
      } else {
        output.push(message);
      }
    }
    return output;
  }, [messages]);

  return (
    <div
      className={`flex justify-start items-start w-full md:p-0 sm:p-4 pt-0 transition-all  duration-300`}
    >
      <div className="flex flex-col gap-4 w-full relative z-10 rounded-lg">
        <div ref={messagesTopRef} />
        {messages
          .filter((m) => m.type === "User")
          .map((message, index) => (
            <div key={`${index}-${message.id}-message`} className="w-full flex">
              <UserMessageDisplay
                onClick={() => setCollapsed((prev) => !prev)}
                text={(message.payload as UserPayload).objects[0]}
                collapsed={collapsed}
              />
            </div>
          ))}
        {!collapsed && messages.length < 2 && backendOnline && !finished && (
          <div className="w-full flex-col flex gap-2 justify-start items-start fade-in">
            <Skeleton className="w-full h-[1rem]" />
            <Skeleton className="w-1/2 h-[1rem]" />
            <Skeleton className="w-2/5 h-[1rem]" />
            <Skeleton className="w-2/5 h-[1rem]" />
          </div>
        )}
        {!collapsed && (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-5">
              {outputItems.map((message, index) => (
                <div key={`${index}-${message.id}-processed-item`} className="w-full flex">
                  {message.type === "result" && (
                    <ResultItemDisplay payload={message.payload as ResultPayload} />
                  )}
                  {message.type === "text" && (
                    <div className="w-full flex flex-col justify-start items-start ">
                      <TextDisplay payload={(message.payload as ResponsePayload).objects} />
                    </div>
                  )}
                </div>
              ))}
            </div>
            {messages
              .filter((m) => m.type === "suggestion")
              .map((message, index) => (
                <div key={`${index}-${message.id}-message`} className="w-full flex">
                  {isLastQuery && (
                    <SuggestionDisplay
                      payload={message.payload as SuggestionPayload}
                      handleSendQuery={handleSendQuery}
                    />
                  )}
                </div>
              ))}
          </div>
        )}
        {!collapsed && <div ref={messagesEndRef} />}
        {!backendOnline && (
          <div className="w-full flex justify-center items-center">
            <p className="text-primary text-sm shine">
              Connection lost. Reconnecting...
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default RenderChat;
