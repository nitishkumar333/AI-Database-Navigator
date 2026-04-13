"use client";

import React, { useContext, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CollectionContext, Connection } from "../components/contexts/CollectionContext";
import { QueryContext } from "../components/contexts/SocketContext";
import { ToastContext } from "../components/contexts/ToastContext";
import { host } from "../components/host";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  GoDatabase,
  GoPlus,
  GoTrash,
  GoCheck,
  GoX,
} from "react-icons/go";
import { HiOutlineBookOpen } from "react-icons/hi2";
import { FaSpinner } from "react-icons/fa";
import { IoCheckmarkCircle, IoEllipseOutline } from "react-icons/io5";

type TableInfo = {
  name: string;
  column_count: number;
};

type KnowledgeEntry = {
  id: number;
  connection_id: number;
  table_name: string;
  table_description: string;
  column_descriptions: Record<string, string>;
  sample_queries: string[];
};

type KnowledgeBaseGroup = {
  id: number;
  connection_id: number;
  name: string;
  tables: KnowledgeEntry[];
  created_at: string;
};

export default function KnowledgeBasePage() {
  const { connections } = useContext(CollectionContext);
  const { getToken, clearAuth } = useContext(QueryContext);
  const { showErrorToast, showSuccessToast } = useContext(ToastContext);

  const [selectedConnection, setSelectedConnection] = useState<Connection | null>(null);
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [loadingTables, setLoadingTables] = useState(false);
  
  // Group creation state
  const [groupName, setGroupName] = useState("");
  const [selectedTables, setSelectedTables] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  // Existing groups
  const [kbGroups, setKbGroups] = useState<KnowledgeBaseGroup[]>([]);
  const [loadingGroups, setLoadingGroups] = useState(false);
  const [autoDescribing, setAutoDescribing] = useState(false);

  const authHeaders = () => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${getToken()}`,
  });

  // Auto-select first connection
  useEffect(() => {
    if (connections.length > 0 && !selectedConnection) {
      setSelectedConnection(connections[0]);
    }
  }, [connections]);

  // Fetch tables & existing groups when connection changes
  useEffect(() => {
    if (selectedConnection) {
      fetchTables(selectedConnection.id);
      fetchKnowledgeGroups(selectedConnection.id);
      
      // Reset form state
      setGroupName("");
      setSelectedTables(new Set());
    }
  }, [selectedConnection]);

  const fetchTables = async (connId: number) => {
    setLoadingTables(true);
    try {
      const response = await fetch(`${host}/api/schema/${connId}/tables`, {
        headers: authHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setTables(data);
      } else if (response.status === 401) {
        clearAuth();
      }
    } catch (e) {
      console.error("Failed to fetch tables:", e);
    }
    setLoadingTables(false);
  };

  const fetchKnowledgeGroups = async (connId: number) => {
    setLoadingGroups(true);
    try {
      const response = await fetch(`${host}/api/knowledge/${connId}/groups`, {
        headers: authHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setKbGroups(data);
      } else if (response.status === 401) {
        clearAuth();
      }
    } catch (e) {
      console.error("Failed to fetch knowledge base groups:", e);
    }
    setLoadingGroups(false);
  };

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
    if (!selectedConnection || selectedTables.size === 0 || groupName.trim() === "") return;
    setSaving(true);
    try {
      const response = await fetch(
        `${host}/api/knowledge/${selectedConnection.id}/group`,
        {
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({
            name: groupName.trim(),
            table_names: Array.from(selectedTables),
          }),
        }
      );
      if (response.ok) {
        showSuccessToast(
          "Knowledge Base Created",
          `Created "${groupName.trim()}" containing ${selectedTables.size} tables`
        );
        setSelectedTables(new Set());
        setGroupName("");
        fetchKnowledgeGroups(selectedConnection.id);
      } else {
        const err = await response.json();
        showErrorToast("Failed", err.detail || "Could not save");
      }
    } catch (e) {
      showErrorToast("Error", String(e));
    }
    setSaving(false);
  };

  const deleteKnowledgeGroup = async (groupId: number) => {
    if (!selectedConnection) return;
    try {
      const response = await fetch(
        `${host}/api/knowledge/group/${groupId}`,
        {
          method: "DELETE",
          headers: authHeaders(),
        }
      );
      if (response.ok) {
        showSuccessToast("Knowledge Base Deleted");
        fetchKnowledgeGroups(selectedConnection.id);
      }
    } catch (e) {
      showErrorToast("Error", String(e));
    }
  };

  const autoDescribe = async () => {
    if (!selectedConnection) return;
    setAutoDescribing(true);
    try {
      const response = await fetch(
        `${host}/api/knowledge/${selectedConnection.id}/auto-describe`,
        {
          method: "POST",
          headers: authHeaders(),
        }
      );
      if (response.ok) {
        const data = await response.json();
        const successCount = data.results.filter(
          (r: { status: string }) => r.status === "success"
        ).length;
        showSuccessToast(
          "Auto-Describe Complete",
          `${successCount}/${data.results.length} tables described`
        );
        fetchKnowledgeGroups(selectedConnection.id);
      }
    } catch (e) {
      showErrorToast("Error", String(e));
    }
    setAutoDescribing(false);
  };

  return (
    <div className="flex flex-col w-full h-screen overflow-y-auto p-2 lg:p-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="flex flex-col gap-6 w-full max-w-4xl mx-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-primary flex items-center gap-3">
              <HiOutlineBookOpen className="text-accent" size={28} />
              Knowledge Bases
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Create named collections of tables to focus the AI's context during chats.
            </p>
          </div>
        </div>

        <Separator />

        {/* Connection selector */}
        <div className="flex flex-col gap-2">
          <label className="text-xs text-muted-foreground font-medium">
            Database Connection
          </label>
          <div className="flex flex-wrap gap-2">
            {connections.map((conn) => (
              <button
                key={conn.id}
                onClick={() => {
                  setSelectedConnection(conn);
                }}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border transition-all duration-200 text-sm ${
                  selectedConnection?.id === conn.id
                    ? "border-accent bg-accent/10 text-accent shadow-sm shadow-accent/10"
                    : "border-foreground hover:border-accent/40 text-primary hover:bg-foreground/30"
                }`}
              >
                <GoDatabase size={16} />
                <span className="font-medium">{conn.name}</span>
                <span className="text-[10px] text-muted-foreground">
                  {conn.db_name}
                </span>
              </button>
            ))}
          </div>
        </div>

        {connections.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-3 p-12 border border-dashed border-foreground rounded-xl">
            <GoDatabase size={40} className="text-muted-foreground" />
            <p className="text-muted-foreground text-sm">
              No database connections found. Add one in Settings first.
            </p>
          </div>
        )}

        {selectedConnection && (
          <>
            {/* Existing KB Groups */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-primary">
                  Your Knowledge Bases
                  {kbGroups.length > 0 && (
                    <span className="ml-2 text-sm font-normal text-muted-foreground">
                      ({kbGroups.length})
                    </span>
                  )}
                </h2>
                {kbGroups.length > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={autoDescribe}
                    disabled={autoDescribing}
                    className="gap-2 text-xs"
                  >
                    {autoDescribing ? (
                      <FaSpinner className="animate-spin" size={12} />
                    ) : (
                      <HiOutlineBookOpen size={14} />
                    )}
                    Generate Missing Table Descriptions (AI)
                  </Button>
                )}
              </div>

              {loadingGroups ? (
                <div className="flex items-center justify-center p-6">
                  <FaSpinner className="animate-spin text-accent" size={20} />
                </div>
              ) : kbGroups.length === 0 ? (
                <div className="p-4 border border-dashed border-foreground rounded-xl text-center">
                  <p className="text-muted-foreground text-sm">
                    No knowledge bases created yet. Use the form below to create one.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3">
                  <AnimatePresence>
                    {kbGroups.map((group, index) => (
                      <motion.div
                        key={group.id}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95 }}
                        transition={{ delay: index * 0.03 }}
                        className="flex flex-col sm:flex-row sm:items-center justify-between p-4 border border-accent/20 rounded-xl bg-accent/5 group hover:border-accent/40 transition-colors gap-4"
                      >
                        <div className="flex flex-col gap-1.5 min-w-0">
                          <h3 className="text-primary text-base font-medium flex items-center gap-2">
                             📚 {group.name}
                          </h3>
                          <div className="flex flex-wrap gap-1.5 mt-1">
                            {group.tables.slice(0, 8).map(t => (
                              <span key={t.id} className="px-2 py-0.5 rounded-full bg-accent/10 border border-accent/20 text-[10px] text-accent">
                                {t.table_name}
                              </span>
                            ))}
                            {group.tables.length > 8 && (
                               <span className="px-2 py-0.5 rounded-full bg-foreground border border-foreground-muted text-[10px] text-muted-foreground">
                                +{group.tables.length - 8} more
                              </span>
                            )}
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => deleteKnowledgeGroup(group.id)}
                          className="text-red-400 hover:text-red-300 hover:bg-red-500/10 flex-shrink-0 self-start sm:self-center"
                        >
                          <GoTrash size={14} className="mr-1.5" />
                          Delete Group
                        </Button>
                      </motion.div>
                    ))}
                  </AnimatePresence>
                </div>
              )}
            </div>

            <Separator />

            {/* Create New Group Section */}
            <div className="flex flex-col gap-5 bg-background p-5 rounded-2xl border border-foreground shadow-sm">
              <h2 className="text-lg font-semibold text-primary">
                Create New Knowledge Base
              </h2>
              
              <div className="flex flex-col gap-2 max-w-md">
                <label className="text-xs text-muted-foreground font-medium">
                  Knowledge Base Name
                </label>
                <input
                  type="text"
                  value={groupName}
                  onChange={(e) => setGroupName(e.target.value)}
                  placeholder="e.g. HR Reports, Sales Data, User Analytics"
                  className="w-full px-3 py-2 bg-transparent border border-foreground rounded-lg text-sm text-primary focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/50 transition-all"
                />
              </div>

              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs text-muted-foreground font-medium">
                    Select Included Tables
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
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 max-h-72 overflow-y-auto pr-2 custom-scrollbar">
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
                            <IoCheckmarkCircle className="text-accent flex-shrink-0" size={18} />
                          ) : (
                            <IoEllipseOutline className="text-muted-foreground flex-shrink-0" size={18} />
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

              {/* Action buttons */}
              <div className="flex justify-end mt-2">
                 <Button
                    onClick={saveKnowledgeGroup}
                    disabled={saving || groupName.trim() === "" || selectedTables.size === 0}
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

            {/* Bottom spacer */}
            <div className="h-8" />
          </>
        )}
      </motion.div>
    </div>
  );
}
