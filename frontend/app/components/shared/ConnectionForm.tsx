"use client";

import React, { useState, useContext } from "react";
import { apiFetch } from "@/app/utils/api";
import { Connection } from "@/app/types/objects";
import { ToastContext } from "../contexts/ToastContext";
import { Button } from "@/components/ui/button";
import {
  GoCheck,
  GoX,
  GoSync,
} from "react-icons/go";
import { FaPlug, FaSpinner } from "react-icons/fa";

const EMPTY_FORM = {
  name: "",
  host: "localhost",
  port: 5432,
  db_name: "",
  username: "postgres",
  password: "",
};

type FormData = typeof EMPTY_FORM;

const FIELDS: {
  key: keyof FormData;
  id: string;
  label: string;
  type: string;
  placeholder: string;
}[] = [
  { key: "name", id: "conn-name", label: "Connection Name", type: "text", placeholder: "My Database" },
  { key: "host", id: "conn-host", label: "Host", type: "text", placeholder: "localhost" },
  { key: "port", id: "conn-port", label: "Port", type: "number", placeholder: "5432" },
  { key: "db_name", id: "conn-dbname", label: "Database Name", type: "text", placeholder: "my_database" },
  { key: "username", id: "conn-username", label: "Username", type: "text", placeholder: "postgres" },
  { key: "password", id: "conn-password", label: "Password", type: "password", placeholder: "••••••••" },
];

interface ConnectionFormProps {
  /** Called after a connection is successfully saved */
  onConnectionSaved?: (connection: Connection) => void;
  /** Whether to show a compact version (for onboarding) */
  compact?: boolean;
}

export default function ConnectionForm({
  onConnectionSaved,
  compact = false,
}: ConnectionFormProps) {
  const { showErrorToast, showSuccessToast } = useContext(ToastContext);

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [saving, setSaving] = useState(false);

  const [connectionString, setConnectionString] = useState("");
  const [formData, setFormData] = useState<FormData>(EMPTY_FORM);

  const handleConnectionStringChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setConnectionString(val);
    
    try {
      const url = new URL(val);
      if (url.protocol === "postgresql:" || url.protocol === "postgres:") {
        const updates: Partial<typeof formData> = {};
        if (url.hostname) updates.host = url.hostname;
        if (url.port) updates.port = parseInt(url.port, 10);
        else updates.port = 5432;
        if (url.pathname && url.pathname !== "/") updates.db_name = url.pathname.slice(1);
        if (url.username) updates.username = decodeURIComponent(url.username);
        if (url.password) updates.password = decodeURIComponent(url.password);
        
        setFormData((prev) => ({ ...prev, ...updates }));
      }
    } catch {
      // Ignore invalid URLs while typing
    }
  };

  const testConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const { name: _name, ...target } = formData; // eslint-disable-line @typescript-eslint/no-unused-vars
      const response = await apiFetch("/api/connections/test", {
        method: "POST",
        body: target,
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
      const response = await apiFetch("/api/connections", {
        method: "POST",
        body: formData,
      });
      if (response.ok) {
        const newConn: Connection = await response.json();
        showSuccessToast(
          "Connection Added",
          `Connected to ${formData.db_name}`
        );
        setFormData(EMPTY_FORM);
        setConnectionString("");
        setTestResult(null);
        onConnectionSaved?.(newConn);
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

  return (
    <div
      className={`border border-accent/30 rounded-xl ${compact ? "p-4" : "p-6"} bg-foreground/30 backdrop-blur-sm`}
    >
      {!compact && (
        <h2 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
          <FaPlug className="text-accent" />
          New PostgreSQL Connection
        </h2>
      )}

      <div className="mb-6 flex flex-col gap-1">
        <label className="text-xs text-muted-foreground font-medium">
          Paste Connection String (Auto-fill)
        </label>
        <input
          id="conn-string"
          type="text"
          value={connectionString}
          onChange={handleConnectionStringChange}
          placeholder="postgresql://user:password@localhost:5432/my_database"
          className="bg-background border border-foreground rounded-lg px-3 py-2 text-sm text-primary w-full focus:outline-none focus:ring-2 focus:ring-accent/50 transition-colors"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {FIELDS.map((field) => (
          <div key={field.key} className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground font-medium">
              {field.label}
            </label>
            <input
              id={field.id}
              type={field.type}
              value={formData[field.key]}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  [field.key]:
                    field.key === "port" ? parseInt(e.target.value) : e.target.value,
                })
              }
              placeholder={field.placeholder}
              className="bg-background border border-foreground rounded-lg px-3 py-2 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent/50"
            />
          </div>
        ))}
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
          {testResult.success ? <GoCheck size={16} /> : <GoX size={16} />}
          {testResult.message}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3 mt-6">
        <Button
          variant="outline"
          onClick={testConnection}
          disabled={testing || !formData.host || !formData.db_name}
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
      </div>
    </div>
  );
}
