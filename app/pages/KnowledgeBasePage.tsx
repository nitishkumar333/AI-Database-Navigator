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

export default function KnowledgeBasePage() {
  const { connections, fetchCollections } = useContext(CollectionContext);
  const { getToken, clearAuth } = useContext(QueryContext);
  const { showErrorToast, showSuccessToast } = useContext(ToastContext);

  const [selectedConnection, setSelectedConnection] = useState<Connection | null>(null);
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [loadingTables, setLoadingTables] = useState(false);
  const [selectedTables, setSelectedTables] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  // Existing knowledge bases
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeEntry[]>([]);
  const [loadingKBs, setLoadingKBs] = useState(false);
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

  // Fetch tables & existing KBs when connection changes
  useEffect(() => {
    if (selectedConnection) {
      fetchTables(selectedConnection.id);
      fetchKnowledgeBases(selectedConnection.id);
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

  const fetchKnowledgeBases = async (connId: number) => {
    setLoadingKBs(true);
    try {
      const response = await fetch(`${host}/api/knowledge/${connId}`, {
        headers: authHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setKnowledgeBases(data);
      } else if (response.status === 401) {
        clearAuth();
      }
    } catch (e) {
      console.error("Failed to fetch knowledge bases:", e);
    }
    setLoadingKBs(false);
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

  const saveKnowledgeBase = async () => {
    if (!selectedConnection || selectedTables.size === 0) return;
    setSaving(true);
    try {
      const response = await fetch(
        `${host}/api/knowledge/${selectedConnection.id}/bulk`,
        {
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({
            table_names: Array.from(selectedTables),
          }),
        }
      );
      if (response.ok) {
        const data = await response.json();
        showSuccessToast(
          "Knowledge Base Updated",
          `${data.length} tables added to knowledge base`
        );
        setSelectedTables(new Set());
        fetchKnowledgeBases(selectedConnection.id);
      } else {
        const err = await response.json();
        showErrorToast("Failed", err.detail || "Could not save");
      }
    } catch (e) {
      showErrorToast("Error", String(e));
    }
    setSaving(false);
  };

  const deleteKBEntry = async (kbId: number) => {
    if (!selectedConnection) return;
    try {
      const response = await fetch(
        `${host}/api/knowledge/${selectedConnection.id}/${kbId}`,
        {
          method: "DELETE",
          headers: authHeaders(),
        }
      );
      if (response.ok) {
        showSuccessToast("Removed from Knowledge Base");
        fetchKnowledgeBases(selectedConnection.id);
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
        fetchKnowledgeBases(selectedConnection.id);
      }
    } catch (e) {
      showErrorToast("Error", String(e));
    }
    setAutoDescribing(false);
  };

  // Tables that are already in the KB
  const kbTableNames = new Set(knowledgeBases.map((kb) => kb.table_name));

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
              Knowledge Base
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Select tables from your database to create a knowledge base. Use it
              in chat to focus queries on specific tables.
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
                  setSelectedTables(new Set());
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
            {/* Existing KB entries */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-primary">
                  Knowledge Base Tables
                  {knowledgeBases.length > 0 && (
                    <span className="ml-2 text-sm font-normal text-muted-foreground">
                      ({knowledgeBases.length} tables)
                    </span>
                  )}
                </h2>
                {knowledgeBases.length > 0 && (
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
                    Auto-Describe with AI
                  </Button>
                )}
              </div>

              {loadingKBs ? (
                <div className="flex items-center justify-center p-6">
                  <FaSpinner className="animate-spin text-accent" size={20} />
                </div>
              ) : knowledgeBases.length === 0 ? (
                <div className="p-4 border border-dashed border-foreground rounded-xl text-center">
                  <p className="text-muted-foreground text-sm">
                    No tables in knowledge base yet. Select tables below to add them.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <AnimatePresence>
                    {knowledgeBases.map((kb, index) => (
                      <motion.div
                        key={kb.id}
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.95 }}
                        transition={{ delay: index * 0.03 }}
                        className="flex items-center justify-between p-3 border border-accent/20 rounded-xl bg-accent/5 group hover:border-accent/40 transition-colors"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <IoCheckmarkCircle className="text-accent flex-shrink-0" size={18} />
                          <div className="min-w-0">
                            <p className="text-primary text-sm font-medium truncate">
                              {kb.table_name}
                            </p>
                            {kb.table_description && (
                              <p className="text-muted-foreground text-[11px] truncate">
                                {kb.table_description}
                              </p>
                            )}
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => deleteKBEntry(kb.id)}
                          className="opacity-0 group-hover:opacity-100 transition-opacity text-red-400 hover:text-red-300 hover:bg-red-500/10 flex-shrink-0"
                        >
                          <GoTrash size={14} />
                        </Button>
                      </motion.div>
                    ))}
                  </AnimatePresence>
                </div>
              )}
            </div>

            <Separator />

            {/* Add tables section */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-primary">
                  Available Tables
                </h2>
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
                    Deselect All
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
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                  {tables.map((table, index) => {
                    const inKB = kbTableNames.has(table.name);
                    const isSelected = selectedTables.has(table.name);

                    return (
                      <motion.button
                        key={table.name}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.02 }}
                        onClick={() => !inKB && toggleTable(table.name)}
                        disabled={inKB}
                        className={`flex items-center gap-3 p-3 rounded-xl border transition-all duration-200 text-left ${
                          inKB
                            ? "border-accent/20 bg-accent/5 opacity-60 cursor-default"
                            : isSelected
                              ? "border-accent bg-accent/10 shadow-sm shadow-accent/10"
                              : "border-foreground hover:border-accent/40 hover:bg-foreground/20"
                        }`}
                      >
                        {inKB ? (
                          <IoCheckmarkCircle className="text-accent flex-shrink-0" size={18} />
                        ) : isSelected ? (
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
                            {inKB && " • In KB"}
                          </p>
                        </div>
                      </motion.button>
                    );
                  })}
                </div>
              )}

              {/* Save button */}
              {selectedTables.size > 0 && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-center justify-between p-4 border border-accent/30 rounded-xl bg-accent/5"
                >
                  <p className="text-sm text-primary">
                    <span className="font-semibold text-accent">
                      {selectedTables.size}
                    </span>{" "}
                    table{selectedTables.size !== 1 ? "s" : ""} selected
                  </p>
                  <div className="flex gap-3">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={deselectAll}
                      className="gap-1.5"
                    >
                      <GoX size={14} />
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      onClick={saveKnowledgeBase}
                      disabled={saving}
                      className="gap-1.5"
                    >
                      {saving ? (
                        <FaSpinner className="animate-spin" size={12} />
                      ) : (
                        <GoPlus size={14} />
                      )}
                      Add to Knowledge Base
                    </Button>
                  </div>
                </motion.div>
              )}
            </div>

            {/* Bottom spacer */}
            <div className="h-8" />
          </>
        )}
      </motion.div>
    </div>
  );
}
