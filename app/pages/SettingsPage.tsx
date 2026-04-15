"use client";

import React, { useContext, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { SessionContext } from "../components/contexts/SessionContext";
import { CollectionContext } from "../components/contexts/CollectionContext";
import { AuthContext } from "../components/contexts/AuthContext";
import { ToastContext } from "../components/contexts/ToastContext";
import { host } from "../components/host";
import ConnectionForm from "../components/shared/ConnectionForm";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { RouterContext } from "../components/contexts/RouterContext";
import {
  GoDatabase,
  GoPlus,
  GoTrash,
} from "react-icons/go";
import { FaSpinner } from "react-icons/fa";

type Connection = {
  id: number;
  name: string;
  host: string;
  port: number;
  db_name: string;
  username: string;
  created_at?: string;
};

export default function SettingsPage() {
  const { id } = useContext(SessionContext);
  const { fetchCollections } = useContext(CollectionContext);
  const { getToken } = useContext(AuthContext);
  const { showErrorToast, showSuccessToast } = useContext(ToastContext);
  const { changePage } = useContext(RouterContext);

  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

  useEffect(() => {
    loadConnections();
  }, []);

  const authHeaders = () => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${getToken()}`,
  });

  const loadConnections = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${host}/api/connections`, {
        headers: authHeaders(),
      });
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
    try {
      const response = await fetch(`${host}/api/connections/${connId}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (response.ok) {
        showSuccessToast("Connection Removed");
        loadConnections();
        fetchCollections();
      }
    } catch (e) {
      showErrorToast("Failed to Delete", String(e));
    }
  };

  const handleConnectionSaved = () => {
    setShowAddForm(false);
    loadConnections();
    fetchCollections();
  };

  return (
    <div className="flex flex-col w-full h-screen overflow-y-auto p-2 lg:p-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="flex flex-col gap-6 w-full max-w-3xl mx-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-primary">Settings</h1>
            <p className="text-sm text-muted-foreground">
              Manage your database connections
            </p>
          </div>
          <Button
            onClick={() => setShowAddForm(!showAddForm)}
            className="gap-2"
          >
            <GoPlus size={16} />
            Add Connection
          </Button>
        </div>

        <Separator />

        {/* Add Connection Form */}
        {showAddForm && (
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
              <Button onClick={() => setShowAddForm(true)} className="gap-2">
                <GoPlus size={14} />
                Add Your First Connection
              </Button>
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
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => deleteConnection(conn.id)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity text-red-400 hover:text-red-300 hover:bg-red-500/10"
                >
                  <GoTrash size={16} />
                </Button>
              </motion.div>
            ))
          )}
        </div>
      </motion.div>
    </div>
  );
}
