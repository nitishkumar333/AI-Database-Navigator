"use client";

import React, { useContext, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { CollectionContext } from "../components/contexts/CollectionContext";
import { AuthContext } from "../components/contexts/AuthContext";
import { ToastContext } from "../components/contexts/ToastContext";
import { apiFetch } from "../utils/api";
import { Connection } from "../types/objects";
import ConnectionForm from "../components/shared/ConnectionForm";
import { Button } from "@/components/ui/button";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { RouterContext } from "../components/contexts/RouterContext";
import { ConversationContext } from "../components/contexts/ConversationContext";
import {
  GoDatabase,
  GoPlus,
  GoTrash,
  GoInfo,
} from "react-icons/go";
import { FaSpinner } from "react-icons/fa";
import ThemeToggle from "../components/shared/ThemeToggle";

export default function SettingsPage() {
  const { fetchConnections } = useContext(CollectionContext);
  const { user } = useContext(AuthContext);
  // The guest account is fixed to the demo shop database.
  const isGuest = !!user?.is_guest;
  const { showErrorToast, showSuccessToast } = useContext(ToastContext);
  const { changePage } = useContext(RouterContext);
  const { dropConversations } = useContext(ConversationContext);

  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  // The connection waiting for delete confirmation, and whether the delete is running.
  const [pendingDelete, setPendingDelete] = useState<Connection | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadConnections();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadConnections = async () => {
    setLoading(true);
    try {
      const response = await apiFetch("/api/connections");
      if (response.ok) {
        const data = await response.json();
        setConnections(data);
      }
    } catch (e) {
      console.error("Failed to load connections:", e);
    }
    setLoading(false);
  };

  const deleteConnection = async (connId: number) => {
    setDeleting(true);
    try {
      const response = await apiFetch(`/api/connections/${connId}`, {
        method: "DELETE",
      });
      if (response.ok) {
        // The backend also deleted every conversation that used this connection.
        const data = await response.json();
        dropConversations(data.deleted_conversations ?? []);
        showSuccessToast("Connection Removed");
        loadConnections();
        fetchConnections();
      } else {
        const data = await response.json().catch(() => ({}));
        showErrorToast("Failed to Delete", data.detail ?? `Error ${response.status}`);
      }
    } catch (e) {
      showErrorToast("Failed to Delete", String(e));
    }
    setDeleting(false);
    setPendingDelete(null);
  };

  const handleConnectionSaved = () => {
    setShowAddForm(false);
    loadConnections();
    fetchConnections();
  };

  return (
    <div className="flex flex-col w-full h-screen overflow-y-auto p-2 pt-6 lg:p-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="flex flex-col gap-6 w-full max-w-3xl mx-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <SidebarTrigger className="lg:hidden flex text-secondary hover:text-primary hover:bg-foreground_alt shrink-0 -ml-1" />
            <div>
              <h1 className="text-2xl font-bold text-primary">Settings</h1>
              <p className="text-sm text-muted-foreground">
                {isGuest
                  ? "The guest account uses the demo shop database"
                  : "Manage your database connections"}
              </p>
            </div>
          </div>
          {!isGuest && (
            <Button
              onClick={() => setShowAddForm(!showAddForm)}
              className="gap-2"
            >
              <GoPlus size={16} />
              Add Connection
            </Button>
          )}
        </div>

        <Separator />

        {isGuest && (
          <div className="flex items-start gap-3 p-4 rounded-xl border border-accent/30 bg-accent/10 text-sm text-primary">
            <GoInfo size={16} className="text-accent mt-0.5 flex-shrink-0" />
            <p>
              Guest users are not allowed to create or delete database
              connections. Sign up for an account to connect your own
              database.
            </p>
          </div>
        )}

        {/* Appearance Settings */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-xl bg-background_alt border border-foreground/70">
          <div className="flex flex-col">
            <h2 className="text-base font-semibold text-primary">Appearance</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Customize your workspace theme
            </p>
          </div>
          <ThemeToggle variant="segmented" />
        </div>

        {/* Add Connection Form */}
        {showAddForm && !isGuest && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
          >
            <ConnectionForm onConnectionSaved={handleConnectionSaved} />
          </motion.div>
        )}

        {/* Connections List */}
        <div className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold text-primary">
            Database Connections
          </h2>

          {loading ? (
            <div className="flex items-center justify-center p-8">
              <FaSpinner className="animate-spin text-accent" size={24} />
            </div>
          ) : connections.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 p-12 border border-dashed border-foreground rounded-xl">
              <GoDatabase size={40} className="text-muted-foreground" />
              <p className="text-muted-foreground text-sm">
                No database connections yet
              </p>
              {!isGuest && (
                <Button onClick={() => setShowAddForm(true)} className="gap-2">
                  <GoPlus size={14} />
                  Add Your First Connection
                </Button>
              )}
            </div>
          ) : (
            connections.map((conn, index) => (
              <motion.div
                key={conn.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.08, duration: 0.4 }}
                className="cursor-pointer flex items-center justify-between p-4 border border-foreground rounded-xl hover:border-accent/40 transition-colors group"
                onClick={() =>
                  changePage(
                    "collection",
                    { collection: conn.name },
                    true
                  )
                }
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center">
                    <GoDatabase className="text-accent" size={20} />
                  </div>
                  <div>
                    <p className="font-medium text-primary">{conn.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {conn.username}@{conn.host}:{conn.port}/{conn.db_name}
                    </p>
                  </div>
                </div>
                {!isGuest && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      // The card itself opens the connection's page.
                      e.stopPropagation();
                      setPendingDelete(conn);
                    }}
                    className="opacity-0 group-hover:opacity-100 transition-opacity text-red-400 hover:text-red-300 hover:bg-red-500/10"
                  >
                    <GoTrash size={16} />
                  </Button>
                )}
              </motion.div>
            ))
          )}
        </div>
      </motion.div>

      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open && !deleting) setPendingDelete(null);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete connection?</DialogTitle>
            <DialogDescription>
              This permanently deletes{" "}
              <span className="font-medium text-primary">{pendingDelete?.name}</span>{" "}
              and everything stored for it: its knowledge bases, query history, schema
              descriptions and search index, and every conversation that used it. Your
              database itself is not changed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              disabled={deleting}
              onClick={() => setPendingDelete(null)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleting}
              onClick={() => pendingDelete && deleteConnection(pendingDelete.id)}
              className="gap-2"
            >
              {deleting ? <FaSpinner className="animate-spin" /> : <GoTrash />}
              {deleting ? "Deleting..." : "Delete connection"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
