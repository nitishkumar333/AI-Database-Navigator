"use client";

import React, { useContext, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { SessionContext } from "../components/contexts/SessionContext";
import { CollectionContext } from "../components/contexts/CollectionContext";
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
  GoSync,
} from "react-icons/go";
import { FaPlug, FaSpinner } from "react-icons/fa";

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
  const { showErrorToast, showSuccessToast } = useContext(ToastContext);

  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [saving, setSaving] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    name: "",
    host: "localhost",
    port: 5432,
    db_name: "",
    username: "postgres",
    password: "",
  });

  // Auth token — we need to get this first
  const [token, setToken] = useState<string | null>(null);

  // Try to auto-login or use stored token
  useEffect(() => {
    const stored = localStorage.getItem("auth_token");
    if (stored) {
      setToken(stored);
    } else {
      // Auto-register/login a default user for the platform
      autoAuth();
    }
  }, []);

  useEffect(() => {
    if (token) {
      loadConnections();
    }
  }, [token]);

  const autoAuth = async () => {
    try {
      // Try to register
      let response = await fetch(`${host}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: "admin@dataanalyst.local",
          username: "admin",
          password: "admin123",
        }),
      });

      // If already registered, login
      if (!response.ok) {
        response = await fetch(`${host}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: "admin@dataanalyst.local",
            password: "admin123",
          }),
        });
      } else {
        // Registration successful, now login
        response = await fetch(`${host}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: "admin@dataanalyst.local",
            password: "admin123",
          }),
        });
      }

      if (response.ok) {
        const data = await response.json();
        localStorage.setItem("auth_token", data.access_token);
        setToken(data.access_token);
      }
    } catch (e) {
      console.error("Auto-auth failed:", e);
    }
  };

  const authHeaders = () => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
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

  const testConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const response = await fetch(`${host}/api/connections/test`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          host: formData.host,
          port: formData.port,
          db_name: formData.db_name,
          username: formData.username,
          password: formData.password,
        }),
      });
      const data = await response.json();
      setTestResult(data);
      if (data.success) {
        showSuccessToast("Connection Successful", data.message);
      } else {
        showErrorToast("Connection Failed", data.message);
      }
    } catch (e) {
      setTestResult({ success: false, message: String(e) });
      showErrorToast("Connection Failed", String(e));
    }
    setTesting(false);
  };

  const saveConnection = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${host}/api/connections`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(formData),
      });
      if (response.ok) {
        showSuccessToast(
          "Connection Added",
          `Connected to ${formData.db_name}`
        );
        setShowAddForm(false);
        setFormData({
          name: "",
          host: "localhost",
          port: 5432,
          db_name: "",
          username: "postgres",
          password: "",
        });
        setTestResult(null);
        loadConnections();
        fetchCollections();
      } else {
        const data = await response.json();
        showErrorToast(
          "Failed to Save",
          data.detail || "Could not save connection"
        );
      }
    } catch (e) {
      showErrorToast("Failed to Save", String(e));
    }
    setSaving(false);
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
            className="border border-accent/30 rounded-xl p-6 bg-foreground/30 backdrop-blur-sm"
          >
            <h2 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
              <FaPlug className="text-accent" />
              New PostgreSQL Connection
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground font-medium">
                  Connection Name
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) =>
                    setFormData({ ...formData, name: e.target.value })
                  }
                  placeholder="My Database"
                  className="bg-background border border-foreground rounded-lg px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent/50"
                />
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground font-medium">
                  Host
                </label>
                <input
                  type="text"
                  value={formData.host}
                  onChange={(e) =>
                    setFormData({ ...formData, host: e.target.value })
                  }
                  placeholder="localhost"
                  className="bg-background border border-foreground rounded-lg px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent/50"
                />
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground font-medium">
                  Port
                </label>
                <input
                  type="number"
                  value={formData.port}
                  onChange={(e) =>
                    setFormData({ ...formData, port: parseInt(e.target.value) })
                  }
                  placeholder="5432"
                  className="bg-background border border-foreground rounded-lg px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent/50"
                />
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground font-medium">
                  Database Name
                </label>
                <input
                  type="text"
                  value={formData.db_name}
                  onChange={(e) =>
                    setFormData({ ...formData, db_name: e.target.value })
                  }
                  placeholder="my_database"
                  className="bg-background border border-foreground rounded-lg px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent/50"
                />
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground font-medium">
                  Username
                </label>
                <input
                  type="text"
                  value={formData.username}
                  onChange={(e) =>
                    setFormData({ ...formData, username: e.target.value })
                  }
                  placeholder="postgres"
                  className="bg-background border border-foreground rounded-lg px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent/50"
                />
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground font-medium">
                  Password
                </label>
                <input
                  type="password"
                  value={formData.password}
                  onChange={(e) =>
                    setFormData({ ...formData, password: e.target.value })
                  }
                  placeholder="••••••••"
                  className="bg-background border border-foreground rounded-lg px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent/50"
                />
              </div>
            </div>

            {/* Test Result */}
            {testResult && (
              <div
                className={`mt-4 p-3 rounded-lg text-sm flex items-center gap-2 ${
                  testResult.success
                    ? "bg-green-500/10 text-green-400 border border-green-500/30"
                    : "bg-red-500/10 text-red-400 border border-red-500/30"
                }`}
              >
                {testResult.success ? (
                  <GoCheck size={16} />
                ) : (
                  <GoX size={16} />
                )}
                {testResult.message}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3 mt-6">
              <Button
                variant="outline"
                onClick={testConnection}
                disabled={
                  testing || !formData.host || !formData.db_name
                }
                className="gap-2"
              >
                {testing ? (
                  <FaSpinner className="animate-spin" size={14} />
                ) : (
                  <GoSync size={14} />
                )}
                Test Connection
              </Button>
              <Button
                onClick={saveConnection}
                disabled={
                  saving ||
                  !formData.name ||
                  !formData.host ||
                  !formData.db_name
                }
                className="gap-2"
              >
                {saving ? (
                  <FaSpinner className="animate-spin" size={14} />
                ) : (
                  <GoCheck size={14} />
                )}
                Save Connection
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setShowAddForm(false);
                  setTestResult(null);
                }}
              >
                Cancel
              </Button>
            </div>
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
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                className="flex items-center justify-between p-4 border border-foreground rounded-xl hover:border-accent/40 transition-colors group"
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
