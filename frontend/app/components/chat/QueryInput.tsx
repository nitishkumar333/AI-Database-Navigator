"use client";

import React, { useEffect, useState, useContext } from "react";
import { FaCircle } from "react-icons/fa";
import { IoArrowUpCircleSharp, IoClose } from "react-icons/io5";
import { RiFlowChart } from "react-icons/ri";
import { FaTrash } from "react-icons/fa";
import { Button } from "@/components/ui/button";
import { TbSettings } from "react-icons/tb";
import { QueryContext } from "../contexts/SocketContext";
import { host } from "../host";

interface KnowledgeBaseGroup {
  id: number;
  connection_id: number;
  name: string;
  tables: string[];
  created_at: string;
}

interface QueryInputProps {
  handleSendQuery: (query: string) => void;
  query_length: number;
  currentStatus: string;
  addDisplacement: (value: number) => void;
  addDistortion: (value: number) => void;
  selectSettings: () => void;
  selectedConnectionId: number | null;
  onConnectionChange: (connectionId: number | null) => void;
  selectedKnowledgeBaseId: number | null;
  onKnowledgeBaseChange: (kbId: number | null) => void;
}

const QueryInput: React.FC<QueryInputProps> = ({
  handleSendQuery,
  query_length,
  currentStatus,
  addDisplacement,
  addDistortion,
  selectSettings,
  selectedConnectionId,
  onConnectionChange,
  selectedKnowledgeBaseId,
  onKnowledgeBaseChange,
}) => {
  const [query, setQuery] = useState("");
  const { getToken, clearAuth } = useContext(QueryContext);
  const [groupDetails, setGroupDetails] = useState<KnowledgeBaseGroup | null>(null);

  const triggerQuery = (_query: string) => {
    if (!selectedKnowledgeBaseId) return;
    if (_query.trim() === "" || currentStatus !== "") return;
    handleSendQuery(_query);
    setQuery("");
  };

  useEffect(() => {
    const fetchGroup = async () => {
      if (!selectedKnowledgeBaseId) {
        setGroupDetails(null);
        return;
      }
      const token = getToken();
      if (!token) return;
      try {
        const url = selectedConnectionId
          ? `${host}/api/knowledge/${selectedConnectionId}/groups`
          : `${host}/api/knowledge/user/groups/all`;
        const response = await fetch(url, {
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        });
        if (response.ok) {
          const data: KnowledgeBaseGroup[] = await response.json();
          const target = data.find(g => g.id === selectedKnowledgeBaseId);
          setGroupDetails(target || null);
        } else if (response.status === 401) {
          clearAuth();
        }
      } catch (e) {
        console.error("Failed to fetch knowledge base groups:", e);
      }
    };
    fetchGroup();
  }, [selectedKnowledgeBaseId, selectedConnectionId]);

  useEffect(() => {
    addDisplacement(0.035);
    addDistortion(0.02);
  }, [query]);

  return (
    <div
      className={`fixed bottom-8 gap-1 flex items-center justify-center flex-col transition-all duration-300 "md:w-[60vw] lg:w-[40vw] w-full p-2 md:p-0 lg:p-0" `}
    >
      <div className="w-full flex justify-between items-center gap-2 mb-2">
        {currentStatus != "" ? (
          <div className="flex gap-2 items-center">
            <FaCircle className="text-lg pulsing" />
            <p className="text-sm shine">{currentStatus}</p>
          </div>
        ) : (
          <div></div>
        )}
      </div>
      {/* Selected KB pill */}
      {groupDetails && (
        <div className="w-full flex flex-wrap gap-1.5 px-1 pb-1">
          <span
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-accent/20 text-accent text-xs font-medium border border-accent/40 shadow-sm"
          >
            📚 {groupDetails.name}
            <span className="text-[10px] opacity-80">({groupDetails.tables.length} tables)</span>
            <button
              onClick={() => onKnowledgeBaseChange(null)}
              className="hover:text-red-400 transition-colors ml-1"
            >
              <IoClose size={14} />
            </button>
          </span>
        </div>
      )}
      <div
        className={`w-full flex gap-2 rounded-xl text-primary placeholder:text-secondary`}
      >
        <div
          className={`flex w-full bg-background_alt border border-foreground_alt p-2 rounded-xl items-center flex-col`}
        >
          <textarea
            disabled={!selectedKnowledgeBaseId}
            placeholder={
              !selectedKnowledgeBaseId
                ? "Please select a Knowledge Base to chat..."
                : query_length !== 0
                  ? "Ask a follow up question..."
                  : "What will you ask today?"
            }
            className={`w-full p-2 bg-transparent ${!selectedKnowledgeBaseId ? "cursor-not-allowed opacity-50" : ""} placeholder:text-secondary outline-none text-sm leading-tight min-h-[5vh] max-h-[10vh] rounded-xl flex items-center justify-center`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                triggerQuery(query);
              }
            }}
            style={{
              paddingTop: query_length === 0 ? "8px" : "6px",
              display: "flex",
              alignItems: "center",
              resize: "none",
            }}
          />
          <div className="flex justify-end gap-1 w-full">
            <Button
              variant="ghost"
              size={"icon"}
              disabled={!selectedKnowledgeBaseId || query.trim() === ""}
              onClick={() => triggerQuery(query)}
            >
              <IoArrowUpCircleSharp size={16} />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default QueryInput;
