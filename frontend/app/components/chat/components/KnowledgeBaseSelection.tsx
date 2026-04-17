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

interface KnowledgeBaseGroup {
  id: number;
  connection_id: number;
  name: string;
  tables: string[];
  created_at: string;
}

interface KnowledgeBaseSelectionProps {
  selectedConnectionId: number | null;
  selectedKnowledgeBaseId: number | null;
  onKnowledgeBaseChange: (kbId: number | null) => void;
  onLoadingChange?: (loading: boolean) => void;
}

const KnowledgeBaseSelection: React.FC<KnowledgeBaseSelectionProps> = ({
  selectedConnectionId,
  selectedKnowledgeBaseId,
  onKnowledgeBaseChange,
  onLoadingChange,
}) => {
  const { getToken, clearAuth } = useContext(QueryContext);
  const [allGroups, setAllGroups] = useState<KnowledgeBaseGroup[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchKnowledgeBases();
  }, [selectedConnectionId]);

  const fetchKnowledgeBases = async () => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    if (onLoadingChange) onLoadingChange(true);
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
        const data = await response.json();
        setAllGroups(data);
        if (data.length > 0 && selectedKnowledgeBaseId === null) {
          onKnowledgeBaseChange(data[0].id);
        }
      } else if (response.status === 401) {
        clearAuth();
      }
    } catch (e) {
      console.error("Failed to fetch knowledge base groups:", e);
    }
    setLoading(false);
    if (onLoadingChange) onLoadingChange(false);
  };

  const toggleGroup = (groupId: number) => {
    if (selectedKnowledgeBaseId === groupId) {
      onKnowledgeBaseChange(null);
    } else {
      onKnowledgeBaseChange(groupId);
    }
  };

  const selectedGroup = allGroups.find(g => g.id === selectedKnowledgeBaseId);

  if (allGroups.length === 0 && !loading) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size={selectedKnowledgeBaseId ? "default" : "icon"}
          className={`gap-1.5 ${selectedKnowledgeBaseId ? "text-accent text-xs px-2" : ""}`}
        >
          <HiOutlineBookOpen
            className={selectedKnowledgeBaseId ? "text-accent" : "text-primary"}
            size={14}
          />
          {selectedGroup && (
            <span className="truncate max-w-[120px]">{selectedGroup.name}</span>
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
        ) : allGroups.length === 0 ? (
          <div className="p-3 text-xs text-muted-foreground text-center">
            No knowledge base groups found. Create one in the Knowledge Base page.
          </div>
        ) : (
          allGroups.map((group) => (
            <DropdownMenuCheckboxItem
              key={group.id}
              checked={selectedKnowledgeBaseId === group.id}
              onCheckedChange={() => toggleGroup(group.id)}
              onSelect={(e) => e.preventDefault()}
              className="flex flex-col items-start"
            >
              <p className="text-primary text-xs font-medium">{group.name}</p>
              <p className="text-muted-foreground text-[10px] truncate max-w-[200px]">
                {group.tables.length} table{group.tables.length === 1 ? '' : 's'}
              </p>
            </DropdownMenuCheckboxItem>
          ))
        )}
        {selectedKnowledgeBaseId !== null && (
          <>
            <DropdownMenuSeparator />
            <button
              onClick={() => onKnowledgeBaseChange(null)}
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
