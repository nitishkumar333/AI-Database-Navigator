"use client";

import React, { useContext, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CollectionContext, Connection } from "../components/contexts/CollectionContext";
import { AuthContext } from "../components/contexts/AuthContext";
import { ToastContext } from "../components/contexts/ToastContext";
import { host } from "../components/host";
import KnowledgeBaseForm from "../components/shared/KnowledgeBaseForm";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  GoDatabase,
  GoTrash,
} from "react-icons/go";
import { HiOutlineBookOpen } from "react-icons/hi2";
import { FaSpinner } from "react-icons/fa";

type KnowledgeBaseGroup = {
  id: number;
  connection_id: number;
  name: string;
  tables: string[];
  created_at: string;
};

export default function KnowledgeBasePage() {
  const { connections } = useContext(CollectionContext);
  const { getToken, clearAuth } = useContext(AuthContext);
  const { showErrorToast, showSuccessToast } = useContext(ToastContext);

  const [selectedConnection, setSelectedConnection] = useState<Connection | null>(null);
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

  // Fetch existing groups when connection changes
  useEffect(() => {
    if (selectedConnection) {
      fetchKnowledgeGroups(selectedConnection.id);
    }
  }, [selectedConnection]);

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



  const handleKnowledgeBaseCreated = () => {
    if (selectedConnection) {
      fetchKnowledgeGroups(selectedConnection.id);
    }
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
              Create named collections of tables to focus the AI&apos;s context during chats.
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
                              <span key={t} className="px-2 py-0.5 rounded-full bg-accent/10 border border-accent/20 text-[10px] text-accent">
                                {t}
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

            {/* Create New Group — using shared component */}
            <KnowledgeBaseForm
              connectionId={selectedConnection.id}
              onKnowledgeBaseCreated={handleKnowledgeBaseCreated}
            />

            {/* Bottom spacer */}
            <div className="h-8" />
          </>
        )}
      </motion.div>
    </div>
  );
}
