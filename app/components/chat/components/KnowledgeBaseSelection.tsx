"use client";

import React, { useContext, useEffect, useState } from "react";
import { HiOutlineBookOpen } from "react-icons/hi2";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuCheckboxItem,
} from "@/components/ui/dropdown-menu";
import { QueryContext } from "../../contexts/SocketContext";
import { host } from "../../host";

interface KnowledgeBaseEntry {
  id: number;
  connection_id: number;
  table_name: string;
  table_description: string;
}

interface KnowledgeBaseSelectionProps {
  selectedConnectionId: number | null;
  selectedKnowledgeBases: KnowledgeBaseEntry[];
  onKnowledgeBaseChange: (kbs: KnowledgeBaseEntry[]) => void;
}

const KnowledgeBaseSelection: React.FC<KnowledgeBaseSelectionProps> = ({
  selectedConnectionId,
  selectedKnowledgeBases,
  onKnowledgeBaseChange,
}) => {
  const { getToken, clearAuth } = useContext(QueryContext);
  const [allKBs, setAllKBs] = useState<KnowledgeBaseEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchKnowledgeBases();
  }, [selectedConnectionId]);

  const fetchKnowledgeBases = async () => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    try {
      const url = selectedConnectionId
        ? `${host}/api/knowledge/${selectedConnectionId}`
        : `${host}/api/knowledge/user/all`;
      const response = await fetch(url, {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
      if (response.ok) {
        const data = await response.json();
        setAllKBs(data);
      } else if (response.status === 401) {
        clearAuth();
      }
    } catch (e) {
      console.error("Failed to fetch knowledge bases:", e);
    }
    setLoading(false);
  };

  const toggleKB = (kb: KnowledgeBaseEntry) => {
    const isSelected = selectedKnowledgeBases.some((s) => s.id === kb.id);
    if (isSelected) {
      onKnowledgeBaseChange(selectedKnowledgeBases.filter((s) => s.id !== kb.id));
    } else {
      onKnowledgeBaseChange([...selectedKnowledgeBases, kb]);
    }
  };

  if (allKBs.length === 0 && !loading) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size={selectedKnowledgeBases.length > 0 ? "default" : "icon"}
          className={`gap-1.5 ${selectedKnowledgeBases.length > 0 ? "text-accent text-xs px-2" : ""}`}
        >
          <HiOutlineBookOpen
            className={selectedKnowledgeBases.length > 0 ? "text-accent" : "text-primary"}
            size={14}
          />
          {selectedKnowledgeBases.length > 0 && (
            <span>{selectedKnowledgeBases.length} tables</span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-64 max-h-72 overflow-y-auto">
        <DropdownMenuLabel className="text-secondary">
          Knowledge Base Tables
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {loading ? (
          <div className="p-3 text-xs text-muted-foreground text-center">
            Loading...
          </div>
        ) : allKBs.length === 0 ? (
          <div className="p-3 text-xs text-muted-foreground text-center">
            No knowledge base entries found. Create some in the Knowledge Base page.
          </div>
        ) : (
          allKBs.map((kb) => (
            <DropdownMenuCheckboxItem
              key={kb.id}
              checked={selectedKnowledgeBases.some((s) => s.id === kb.id)}
              onCheckedChange={() => toggleKB(kb)}
              onSelect={(e) => e.preventDefault()}
              className="flex flex-col items-start"
            >
              <p className="text-primary text-xs font-medium">{kb.table_name}</p>
              {kb.table_description && (
                <p className="text-muted-foreground text-[10px] truncate max-w-[200px]">
                  {kb.table_description}
                </p>
              )}
            </DropdownMenuCheckboxItem>
          ))
        )}
        {selectedKnowledgeBases.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <button
              onClick={() => onKnowledgeBaseChange([])}
              className="w-full text-xs text-red-400 hover:text-red-300 p-2 text-center transition-colors"
            >
              Clear Selection
            </button>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default KnowledgeBaseSelection;
