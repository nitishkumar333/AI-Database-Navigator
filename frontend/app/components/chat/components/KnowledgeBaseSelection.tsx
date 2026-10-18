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
import { AuthContext } from "../../contexts/AuthContext";
import { apiFetch } from "@/app/utils/api";
import { KnowledgeBaseGroup } from "@/app/types/objects";

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
  const { logout } = useContext(AuthContext);
  const [allGroups, setAllGroups] = useState<KnowledgeBaseGroup[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchKnowledgeBases();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedConnectionId]);

  const fetchKnowledgeBases = async () => {
    setLoading(true);
    onLoadingChange?.(true);
    try {
      const response = await apiFetch(
        selectedConnectionId
          ? `/api/knowledge/${selectedConnectionId}/groups`
          : "/api/knowledge/user/groups/all"
      );
      if (response.ok) {
        const data: KnowledgeBaseGroup[] = await response.json();
        setAllGroups(data);
        // Select the first group when none is selected or the selected one is
        // gone (its connection was deleted).
        if (!data.some((g) => g.id === selectedKnowledgeBaseId)) {
          onKnowledgeBaseChange(data.length > 0 ? data[0].id : null);
        }
      } else if (response.status === 401) {
        logout();
      }
    } catch (e) {
      console.error("Failed to fetch knowledge base groups:", e);
    }
    setLoading(false);
    onLoadingChange?.(false);
  };

  const toggleGroup = (groupId: number) => {
    onKnowledgeBaseChange(selectedKnowledgeBaseId === groupId ? null : groupId);
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
