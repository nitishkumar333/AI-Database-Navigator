"use client";

import React, { useContext, useEffect, useState } from "react";
import { AuthContext } from "../contexts/AuthContext";
import { ToastContext } from "../contexts/ToastContext";
import { apiFetch } from "@/app/utils/api";
import { TableInfo } from "@/app/types/objects";
import { Button } from "@/components/ui/button";
import { GoPlus } from "react-icons/go";
import { FaSpinner } from "react-icons/fa";
import { IoCheckmarkCircle, IoEllipseOutline } from "react-icons/io5";

interface KnowledgeBaseFormProps {
  /** The connection whose tables the knowledge base groups */
  connectionId: number;
  /** Called after a knowledge base group is successfully created */
  onKnowledgeBaseCreated?: () => void;
  /** Whether to show a compact version */
  compact?: boolean;
}

export default function KnowledgeBaseForm({
  connectionId,
  onKnowledgeBaseCreated,
  compact = false,
}: KnowledgeBaseFormProps) {
  const { logout } = useContext(AuthContext);
  const { showErrorToast, showSuccessToast } = useContext(ToastContext);

  const [tables, setTables] = useState<TableInfo[]>([]);
  const [loadingTables, setLoadingTables] = useState(false);
  const [groupName, setGroupName] = useState("");
  const [selectedTables, setSelectedTables] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  // Fetch tables when the connection changes
  useEffect(() => {
    const fetchTables = async () => {
      setLoadingTables(true);
      try {
        const response = await apiFetch(`/api/schema/${connectionId}/tables`);
        if (response.ok) {
          setTables(await response.json());
        } else if (response.status === 401) {
          logout();
        }
      } catch (e) {
        console.error("Failed to fetch tables:", e);
      }
      setLoadingTables(false);
    };
    fetchTables();
    setGroupName("");
    setSelectedTables(new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionId]);

  const toggleTable = (tableName: string) => {
    setSelectedTables((prev) => {
      const next = new Set(prev);
      if (next.has(tableName)) {
        next.delete(tableName);
      } else {
        next.add(tableName);
      }
      return next;
    });
  };

  const selectAll = () => {
    setSelectedTables(new Set(tables.map((t) => t.name)));
  };

  const deselectAll = () => {
    setSelectedTables(new Set());
  };

  const saveKnowledgeGroup = async () => {
    if (selectedTables.size === 0 || groupName.trim() === "") return;
    setSaving(true);
    try {
      const response = await apiFetch(`/api/knowledge/${connectionId}/group`, {
        method: "POST",
        body: {
          name: groupName.trim(),
          table_names: Array.from(selectedTables),
        },
      });
      if (response.ok) {
        showSuccessToast(
          "Knowledge Base Created",
          `Created "${groupName.trim()}" containing ${selectedTables.size} tables`
        );
        setSelectedTables(new Set());
        setGroupName("");
        onKnowledgeBaseCreated?.();
      } else {
        const err = await response.json();
        showErrorToast("Failed", err.detail || "Could not save");
      }
    } catch (e) {
      showErrorToast("Error", String(e));
    }
    setSaving(false);
  };

  return (
    <div
      className={`flex flex-col gap-5 bg-background ${compact ? "p-4" : "p-5"} rounded-2xl border border-foreground shadow-sm`}
    >
      {!compact && (
        <h2 className="text-lg font-semibold text-primary">
          Create New Knowledge Base
        </h2>
      )}

      {/* KB Name */}
      <div className="flex flex-col gap-2 max-w-md">
        <label className="text-xs text-muted-foreground font-medium">
          Knowledge Base Name
        </label>
        <input
          id="kb-name"
          type="text"
          value={groupName}
          onChange={(e) => setGroupName(e.target.value)}
          placeholder="e.g. HR Reports, Sales Data, User Analytics"
          className="w-full px-3 py-2 bg-transparent border border-foreground rounded-lg text-sm text-primary focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/50 transition-all"
        />
      </div>

      {/* Table selector */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <label className="text-xs text-muted-foreground font-medium">
            Select Tables to Include
          </label>
          <div className="flex gap-2">
            <button
              onClick={selectAll}
              className="text-xs text-accent hover:text-accent/80 transition-colors"
            >
              Select All
            </button>
            <span className="text-muted-foreground text-xs">|</span>
            <button
              onClick={deselectAll}
              className="text-xs text-muted-foreground hover:text-primary transition-colors"
            >
              Clear
            </button>
          </div>
        </div>

        {loadingTables ? (
          <div className="flex items-center justify-center p-8">
            <FaSpinner className="animate-spin text-accent" size={24} />
          </div>
        ) : tables.length === 0 ? (
          <div className="p-6 border border-dashed border-foreground rounded-xl text-center">
            <p className="text-muted-foreground text-sm">
              No tables found in this database
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 max-h-72 overflow-y-auto pr-2">
            {tables.map((table) => {
              const isSelected = selectedTables.has(table.name);
              return (
                <button
                  key={table.name}
                  onClick={() => toggleTable(table.name)}
                  className={`flex items-center gap-3 p-3 rounded-xl border transition-all duration-200 text-left ${
                    isSelected
                      ? "border-accent bg-accent/10 shadow-sm shadow-accent/10"
                      : "border-foreground hover:border-accent/40 hover:bg-foreground/20"
                  }`}
                >
                  {isSelected ? (
                    <IoCheckmarkCircle
                      className="text-accent flex-shrink-0"
                      size={18}
                    />
                  ) : (
                    <IoEllipseOutline
                      className="text-muted-foreground flex-shrink-0"
                      size={18}
                    />
                  )}
                  <div className="min-w-0">
                    <p className="text-primary text-sm font-medium truncate">
                      {table.name}
                    </p>
                    <p className="text-muted-foreground text-[10px]">
                      {table.column_count} columns
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Save button */}
      <div className="flex justify-end mt-2">
        <Button
          onClick={saveKnowledgeGroup}
          disabled={
            saving || groupName.trim() === "" || selectedTables.size === 0
          }
          className="gap-2 shadow-md hover:shadow-lg transition-shadow"
        >
          {saving ? (
            <FaSpinner className="animate-spin" size={14} />
          ) : (
            <GoPlus size={16} />
          )}
          Create Knowledge Base
        </Button>
      </div>
    </div>
  );
}
