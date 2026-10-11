"use client";

import React, { useContext, useEffect, useState } from "react";

import {
  Message,
  ResponsePayload,
  ResultPayload,
  TextPayload,
  NERPayload,
  RateLimitPayload,
  SuggestionPayload,
} from "@/app/types/chat";

import UserMessageDisplay from "./displays/SystemMessages/UserMessageDisplay";
import ErrorMessageDisplay from "./displays/SystemMessages/ErrorMessageDisplay";
import TextDisplay from "./displays/Generic/TextDisplay";
import WarningDisplay from "./displays/SystemMessages/WarningDisplay";
import InfoMessageDisplay from "./displays/SystemMessages/InfoMessageDisplay";
import { Skeleton } from "@/components/ui/skeleton";
import { QueryContext } from "../contexts/SocketContext";
import RateLimitMessageDisplay from "./displays/SystemMessages/RateLimitMessageDisplay";
import SuggestionDisplay from "./displays/SystemMessages/SuggestionDisplay";
import RenderDisplay from "./RenderDisplay";
import { ChatContext } from "../contexts/ChatContext";
import CodeView from "./displays/QueryCode/CodeView";
import ProductView from "./displays/Product/ProductView";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

interface RenderChatProps {
  messages: Message[];
  _collapsed: boolean;
  messagesEndRef: React.RefObject<HTMLDivElement>;
  finished: boolean;
  NER: NERPayload | null;
  handleSendQuery: (query: string) => void;
  isLastQuery: boolean;
}
interface ResultItemDisplayProps {
  message: Message;
  index: number;
  handleResultPayloadChange: (
    type: string,
    /* eslint-disable @typescript-eslint/no-explicit-any */
    payload: any
  ) => void;
}

const ResultItemDisplay: React.FC<ResultItemDisplayProps> = ({
  message,
  index,
  handleResultPayloadChange,
}) => {
  const [showCode, setShowCode] = useState(true);

  return (
    <div className="w-full flex flex-col justify-start items-start gap-3">
      {showCode && (
        <div className="w-full mt-2">
          <CodeView
            payload={[message.payload as ResultPayload]}
            handleViewChange={() => setShowCode(false)}
          />
        </div>
      )}
      <RenderDisplay
        payload={message.payload as ResultPayload}
        index={index}
        messageId={message.id}
        handleResultPayloadChange={handleResultPayloadChange}
      />
    </div>
  );
};

const RenderChat: React.FC<RenderChatProps> = ({
  messages,
  _collapsed,
  messagesEndRef,
  finished,
  NER,
  handleSendQuery,
  isLastQuery,
}) => {
  const [displayMessages, setDisplayMessages] = useState<Message[]>([]);
  const [collapsed, setCollapsed] = useState<boolean>(_collapsed);
  const { backendOnline } = useContext(QueryContext);
  const {
    buildRefMap,
    currentView,
    currentResultPayload,
    currentResultType,
    handleViewChange,
    handleResultPayloadChange,
  } = useContext(ChatContext);

  const messagesTopRef = React.useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (displayMessages.length > 0) {
      messagesTopRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [displayMessages.length]);

  useEffect(() => {
    setDisplayMessages(messages);
    buildRefMap(messages);
  }, [messages]);

  const processedOutputItems = React.useMemo(() => {
    const output: Message[] = [];
    const messagesToProcess = displayMessages.filter(
      (m) => m.type !== "User" && m.type !== "suggestion"
    );

    let i = 0;
    while (i < messagesToProcess.length) {
      const currentMessage = messagesToProcess[i];

      if (
        currentMessage.type === "text" &&
        (currentMessage.payload as ResponsePayload).type === "response"
      ) {
        const currentResponsePayload =
          currentMessage.payload as ResponsePayload;
        const combinedTextPayloads: TextPayload[] = Array.isArray(
          currentResponsePayload.objects
        )
          ? [...(currentResponsePayload.objects as TextPayload[])]
          : [];

        let j = i + 1;

        while (j < messagesToProcess.length) {
          const nextMessage = messagesToProcess[j];
          if (
            nextMessage.type === "text" &&
            (nextMessage.payload as ResponsePayload).type === "response"
          ) {
            const nextResponsePayloadObjects = (
              nextMessage.payload as ResponsePayload
            ).objects;
            if (Array.isArray(nextResponsePayloadObjects)) {
              combinedTextPayloads.push(
                ...(nextResponsePayloadObjects as TextPayload[])
              );
            }
            j++;
          } else {
            break;
          }
        }

        if (j > i + 1) {
          const syntheticMessage: Message = {
            type: "text",
            id: currentMessage.id,
            user_id: currentMessage.user_id,
            conversation_id: currentMessage.conversation_id,
            query_id: currentMessage.query_id,
            payload: {
              type: "response",
              metadata: currentResponsePayload.metadata,
              objects: combinedTextPayloads,
            } as ResponsePayload,
          };
          output.push(syntheticMessage);
          i = j;
          continue;
        }
      }

      output.push(currentMessage);
      i++;
    }
    return output;
  }, [displayMessages]);

  return (
    <div
      className={`flex justify-start items-start w-full md:p-0 sm:p-4 pt-0 transition-all  duration-300`}
    >
      {(currentView === "chat" || currentView === "result") && (
        <div className="flex flex-col gap-4 w-full relative z-10 rounded-lg">
          <div ref={messagesTopRef} />
          {displayMessages
            .filter((m) => m.type === "User")
            .map((message, index) => (
              <div
                key={`${index}-${message.id}-message`}
                className="w-full flex"
              >
                {message.type === "User" && (
                  <UserMessageDisplay
                    NER={NER}
                    onClick={() => setCollapsed((prev) => !prev)}
                    key={`${index}-${message.id}-user`}
                    payload={
                      (message.payload as ResultPayload).objects as string[]
                    }
                    collapsed={collapsed}
                  />
                )}
              </div>
            ))}
          {!collapsed &&
            displayMessages.length < 2 &&
            backendOnline &&
            !finished && (
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
                {processedOutputItems.map((message, index) => {
                  const key = `${index}-${message.id}-processed-item`;

                  return (
                    <div key={key} className="w-full flex">
                      {/* Result Messages */}
                      {message.type === "result" && (
                        <ResultItemDisplay
                          message={message}
                          index={index}
                          handleResultPayloadChange={
                            handleResultPayloadChange
                          }
                        />
                      )}
                      {/* Text Messages */}
                      {message.type === "text" && (
                        <div className="w-full flex flex-col justify-start items-start ">
                          {(message.payload as ResponsePayload).type ===
                            "response" && (
                              <TextDisplay
                                key={`${index}-${message.id}-response`}
                                payload={
                                  (message.payload as ResponsePayload)
                                    .objects as TextPayload[]
                                }
                              />
                            )}
                        </div>
                      )}
                      {/* Error Messages */}
                      {["error", "authentication_error"].includes(message.type) && (
                        <ErrorMessageDisplay
                          key={`${index}-${message.id}-error`}
                          error={(message.payload as TextPayload).text}
                        />
                      )}
                      {["user_timeout_error"].includes(message.type) && (
                        <InfoMessageDisplay
                          key={`${index}-${message.id}-info`}
                          info={(message.payload as TextPayload).text}
                        />
                      )}
                      {["rate_limit_error"].includes(message.type) && (
                        <RateLimitMessageDisplay
                          key={`${index}-${message.id}-info`}
                          payload={message.payload as RateLimitPayload}
                        />
                      )}
                      {message.type === "warning" && (
                        <WarningDisplay
                          key={`${index}-${message.id}-warning`}
                          warning={(message.payload as TextPayload).text}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
              {displayMessages
                .filter((m) => m.type === "suggestion")
                .map((message, index) => (
                  <div
                    key={`${index}-${message.id}-message`}
                    className="w-full flex"
                  >
                    {message.type === "suggestion" && isLastQuery && (
                      <SuggestionDisplay
                        key={`${index}-${message.id}-suggestion`}
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
      )}
      <Dialog
        open={
          currentView === "result" &&
          currentResultType === "product" &&
          !!currentResultPayload
        }
        onOpenChange={(open) => {
          if (!open) handleViewChange("chat");
        }}
      >
        <DialogContent
          aria-describedby={undefined}
          className="w-[95vw] max-w-4xl max-h-[90vh] overflow-hidden bg-background_alt border-foreground_alt rounded-2xl p-0"
        >
          <DialogTitle className="sr-only">
            {currentResultPayload?.name ||
              currentResultPayload?.title ||
              "Product details"}
          </DialogTitle>
          {currentResultPayload && (
            <ProductView product={currentResultPayload} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default RenderChat;
