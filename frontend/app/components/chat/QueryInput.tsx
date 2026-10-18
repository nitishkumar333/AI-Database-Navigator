"use client";

import React, { useState } from "react";
import { FaCircle } from "react-icons/fa";
import { IoArrowUpCircleSharp } from "react-icons/io5";
import { Button } from "@/components/ui/button";

interface QueryInputProps {
  handleSendQuery: (query: string) => void;
  query_length: number;
  currentStatus: string;
  selectedKnowledgeBaseId: number | null;
  noConnections?: boolean;
}

const QueryInput: React.FC<QueryInputProps> = ({
  handleSendQuery,
  query_length,
  currentStatus,
  selectedKnowledgeBaseId,
  noConnections = false,
}) => {
  const [query, setQuery] = useState("");
  const triggerQuery = (_query: string) => {
    if (!selectedKnowledgeBaseId) return;
    if (_query.trim() === "" || currentStatus !== "") return;
    handleSendQuery(_query);
    setQuery("");
  };

  return (
    <>
      {/* Fade layer: sits under the input (z-20 < z-30), doesn't block clicks */}
      <div
        aria-hidden
        className="fixed bottom-0 left-0 w-full lg:left-64 lg:w-[calc(100%-16rem)] h-32 sm:h-40 z-20 pointer-events-none bg-gradient-to-t from-background via-background/80 to-transparent"
      />
      <div
        className="fixed bottom-2 sm:bottom-4 md:bottom-8 w-full md:w-[85vw] lg:w-[70vw] px-3 md:px-0 flex flex-col items-center justify-center gap-1 transition-all duration-300 z-30 pointer-events-auto"
      >
        {currentStatus !== "" && (
          <div className="w-full flex justify-between items-center gap-2 mb-1 px-1">
            <div className="flex gap-2 items-center">
              <FaCircle className="text-xs pulsing" />
              <p className="text-xs shine">{currentStatus}</p>
            </div>
          </div>
        )}
        <div
          className="w-full flex gap-2 rounded-xl text-primary placeholder:text-secondary"
        >
          <div className="flex w-full bg-background_alt border border-foreground_alt p-2 rounded-xl items-center gap-2 shadow-[0_-10px_30px_-5px_rgba(0,0,0,0.35)]">
            <textarea
              disabled={!selectedKnowledgeBaseId}
              placeholder={
                noConnections
                  ? "Add a database connection to start chatting..."
                  : !selectedKnowledgeBaseId
                  ? "Please select a Knowledge Base to chat..."
                  : query_length !== 0
                    ? "Ask a follow up question..."
                    : "What will you ask today?"
              }
              className={`flex-1 w-full p-2 bg-transparent ${!selectedKnowledgeBaseId ? "cursor-not-allowed opacity-50" : ""
                } placeholder:text-secondary outline-none text-sm rounded-xl resize-none`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  triggerQuery(query);
                }
              }}
              style={{
                height: "44px",
                lineHeight: "28px",
                paddingTop: "8px",
                paddingBottom: "8px",
              }}
            />
            <div className="flex items-center justify-end shrink-0">
              <Button
                variant="ghost"
                size={"icon"}
                disabled={!selectedKnowledgeBaseId || query.trim() === ""}
                onClick={() => triggerQuery(query)}
              >
                <IoArrowUpCircleSharp size={18} />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default QueryInput;
