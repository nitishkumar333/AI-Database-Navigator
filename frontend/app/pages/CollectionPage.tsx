"use client";

import React, { useContext, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { apiFetch } from "../utils/api";
import { TableInfo } from "../types/objects";
import { RouterContext } from "../components/contexts/RouterContext";
import { CollectionContext } from "../components/contexts/CollectionContext";
import {
  GoTable,
  GoKey,
  GoLink,
  GoArrowLeft,
  GoDatabase,
  GoEye,
  GoSync,
} from "react-icons/go";
import { FaSpinner } from "react-icons/fa";
import { useSearchParams } from "next/navigation";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import EditableDescription from "../components/explorer/EditableDescription";

type ColumnInfo = {
  name: string;
  type: string;
  nullable: boolean;
  default: string | null;
  is_primary_key: boolean;
  foreign_key: {
    referred_table: string;
    referred_columns: string[];
  } | null;
};

type ColumnDetails = {
  name: string;
  description: string | null;
  description_source: string | null;
  sample_values: string[];
  text_format: string | null;
  distinct_count: number | null;
};

type TableDetails = {
  name: string;
  row_count: number | null;
  description: string | null;
  description_source: string | null;
  columns: ColumnDetails[];
};

type ProfileStatus = {
  status: string; // none | pending | running | ready | failed
  description_status: string; // idle | running | done | partial | failed | disabled
  error?: string | null;
  profiled_at?: string | null;
};

const isBusy = (p: ProfileStatus | null) =>
  !!p &&
  (["pending", "running"].includes(p.status) ||
    p.description_status === "running");

type PreviewData = {
  columns: string[];
  rows: Record<string, unknown>[];
};

export default function CollectionPage() {
  const searchParams = useSearchParams();
  const collectionName = searchParams.get("collection") || "";
  const { changePage } = useContext(RouterContext);
  const { connections } = useContext(CollectionContext);

  const [tables, setTables] = useState<TableInfo[]>([]);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [columns, setColumns] = useState<ColumnInfo[]>([]);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingColumns, setLoadingColumns] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [activeTab, setActiveTab] = useState<"columns" | "preview">("preview");
  const [details, setDetails] = useState<TableDetails | null>(null);
  const [profile, setProfile] = useState<ProfileStatus | null>(null);

  const connName = collectionName.split(" (")[0];
  const [connId, setConnId] = useState<number | null>(null);

  const tablePath = (cId: number, tableName: string) =>
    `/api/schema/${cId}/tables/${tableName}`;

  // Descriptions + profile facts; 404 just means "not profiled yet".
  const loadDetails = async (cId: number, tableName: string) => {
    try {
      const res = await apiFetch(
        `${tablePath(cId, encodeURIComponent(tableName))}/details`
      );
      setDetails(res.ok ? await res.json() : null);
    } catch (e) {
      console.error("Failed to load table details:", e);
      setDetails(null);
    }
  };

  const fetchProfile = async (cId: number): Promise<ProfileStatus | null> => {
    const res = await apiFetch(`/api/schema/${cId}/profile`);
    return res.ok ? res.json() : null;
  };

  const refreshProfile = async () => {
    if (!connId) return;
    await apiFetch(`/api/schema/${connId}/profile/refresh`, {
      method: "POST",
      body: {},
    });
    setProfile((p) => ({ ...(p || { description_status: "idle" }), status: "running" }));
  };

  const saveDescription = async (
    tableName: string,
    columnName: string | null,
    text: string
  ) => {
    if (!connId) return;
    const base = tablePath(connId, encodeURIComponent(tableName));
    const url = columnName
      ? `${base}/columns/${encodeURIComponent(columnName)}/description`
      : `${base}/description`;
    const res = await apiFetch(url, { method: "PUT", body: { description: text } });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Could not save description");
    }
    await loadDetails(connId, tableName);
  };

  // While profiling/describing runs in the background, poll its status and
  // refresh the open table once it finishes.
  useEffect(() => {
    if (!connId || !isBusy(profile)) return;
    const timer = setTimeout(async () => {
      const next = await fetchProfile(connId).catch(() => null);
      if (!next) return;
      setProfile(next);
      if (!isBusy(next) && selectedTable) loadDetails(connId, selectedTable);
    }, 4000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile, connId, selectedTable]);

  // Find the connection by name, then load its tables and profile status.
  useEffect(() => {
    const match = connections.find((c) => c.name === connName);
    if (!match || match.id === connId) return;
    setConnId(match.id);
    loadTables(match.id);
    fetchProfile(match.id)
      .then((p) => p && setProfile(p))
      .catch((e) => console.error("Failed to load profile status:", e));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connections, connName]);

  // Auto-select the first table once the tables are loaded
  useEffect(() => {
    if (tables.length > 0 && !selectedTable && connId) {
      loadColumns(tables[0].name);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tables, connId]);

  const loadTables = async (cId: number) => {
    setLoading(true);
    try {
      const response = await apiFetch(`/api/schema/${cId}/tables`);
      if (response.ok) setTables(await response.json());
    } catch (e) {
      console.error("Failed to load tables:", e);
    }
    setLoading(false);
  };

  // Selects a table and loads its columns, preview rows and descriptions.
  const loadColumns = async (tableName: string) => {
    if (!connId) return;
    setLoadingColumns(true);
    setLoadingPreview(true);
    setSelectedTable(tableName);
    setActiveTab("preview");
    setPreview(null);
    setDetails(null);
    try {
      const [colRes, prevRes] = await Promise.all([
        apiFetch(`${tablePath(connId, tableName)}/columns`),
        apiFetch(`${tablePath(connId, tableName)}/preview`),
      ]);
      if (colRes.ok) setColumns(await colRes.json());
      if (prevRes.ok) setPreview(await prevRes.json());
      await loadDetails(connId, tableName);
    } catch (e) {
      console.error("Failed to load table data:", e);
    }
    setLoadingColumns(false);
    setLoadingPreview(false);
  };

  const loadPreview = async (tableName: string) => {
    if (!connId) return;
    setLoadingPreview(true);
    setActiveTab("preview");
    try {
      const response = await apiFetch(`${tablePath(connId, tableName)}/preview`);
      if (response.ok) setPreview(await response.json());
    } catch (e) {
      console.error("Failed to load preview:", e);
    }
    setLoadingPreview(false);
  };

  return (
    <div className="flex flex-col w-full h-full overflow-hidden p-2 pt-0">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 w-full h-full"
      >
        {/* Header */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <SidebarTrigger className="lg:hidden flex text-secondary hover:text-primary hover:bg-foreground_alt shrink-0 -ml-1" />
          <button
            onClick={() => changePage("settings", {}, true)}
            className="text-muted-foreground hover:text-primary transition-colors"
          >
            <GoArrowLeft size={20} />
          </button>
          <GoDatabase className="text-accent" size={20} />
          <div>
            <h1 className="text-xl font-bold text-primary">{connName}</h1>
            <p className="text-xs text-muted-foreground">
              {tables.length} tables found
              {profile && profile.status !== "none" && (
                <>
                  {" · "}
                  {profile.status === "ready"
                    ? `AI context profiled${
                        profile.description_status === "running"
                          ? ", writing descriptions…"
                          : ""
                      }`
                    : profile.status === "failed"
                    ? "Profiling failed"
                    : "Profiling…"}
                </>
              )}
            </p>
          </div>
          {connId && (
            <button
              onClick={refreshProfile}
              disabled={isBusy(profile)}
              title="Re-read the schema, statistics and sample values the AI uses, and describe new or changed tables"
              className="ml-auto flex items-center gap-2 text-xs text-muted-foreground hover:text-accent disabled:opacity-50 border border-foreground rounded-md px-2 py-1"
            >
              <GoSync size={12} className={isBusy(profile) ? "animate-spin" : ""} />
              Re-profile
            </button>
          )}
        </div>

        <Separator />

        {loading ? (
          <div className="flex items-center justify-center flex-1">
            <FaSpinner className="animate-spin text-accent" size={32} />
          </div>
        ) : (
          <div className="flex flex-col md:flex-row gap-4 flex-1 min-h-0 overflow-hidden">
            {/* Table List */}
            <div className="w-full md:w-64 md:min-h-0 flex-shrink-0 flex md:block border border-foreground rounded-xl overflow-y-auto md:overflow-y-auto overflow-x-auto">
              <div className="p-3 border-b border-foreground hidden md:block">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Tables
                </p>
              </div>
              {tables.map((table) => (
                <button
                  key={table.name}
                  onClick={() => loadColumns(table.name)}
                  className={`w-auto md:w-full flex-auto flex-shrink-0 text-left px-4 py-3 text-sm border-r md:border-r-0 md:border-b border-foreground/50 hover:bg-foreground/30 transition-colors flex items-center justify-between gap-3 ${
                    selectedTable === table.name
                      ? "bg-accent/10 text-accent border-b-2 md:border-b-0 md:border-l-2 md:border-l-accent border-b-accent md:border-b-foreground/50"
                      : "text-primary"
                  }`}
                >
                  <span className="flex items-center gap-2 truncate whitespace-nowrap">
                    <GoTable size={14} className="flex-shrink-0"/>
                    {table.name}
                  </span>
                  <span className="text-xs text-muted-foreground hidden md:inline">
                    {table.column_count}
                  </span>
                </button>
              ))}
              {tables.length === 0 && (
                <div className="p-4 text-sm text-muted-foreground text-center">
                  No tables found
                </div>
              )}
            </div>

            {/* Detail Panel */}
            <div className="flex-1 border border-foreground rounded-xl overflow-hidden flex flex-col">
              {selectedTable ? (
                <>
                  {/* Tabs */}
                  <div className="flex items-center gap-0 border-b border-foreground flex-shrink-0">
                    <button
                      onClick={() => {
                        if (selectedTable) loadPreview(selectedTable);
                      }}
                      className={`px-4 py-3 text-sm font-medium transition-colors ${
                        activeTab === "preview"
                          ? "text-accent border-b-2 border-accent bg-accent/5"
                          : "text-muted-foreground hover:text-primary"
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        <GoEye size={14} />
                        Preview Data
                      </span>
                    </button>
                    <button
                      onClick={() => setActiveTab("columns")}
                      className={`px-4 py-3 text-sm font-medium transition-colors ${
                        activeTab === "columns"
                          ? "text-accent border-b-2 border-accent bg-accent/5"
                          : "text-muted-foreground hover:text-primary"
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        <GoKey size={14} />
                        Columns ({columns.length})
                      </span>
                    </button>
                  </div>

                  {/* Tab Content */}
                  <div className="flex-1 overflow-auto">
                    {activeTab === "columns" && (
                      <>
                        {loadingColumns ? (
                          <div className="flex items-center justify-center p-8">
                            <FaSpinner
                              className="animate-spin text-accent"
                              size={20}
                            />
                          </div>
                        ) : (
                          <>
                          {details && (
                            <div className="px-4 py-3 border-b border-foreground flex flex-col gap-1">
                              <span className="text-xs font-semibold text-muted-foreground uppercase">
                                Table description
                                {details.row_count != null &&
                                  ` · ~${details.row_count.toLocaleString()} rows`}
                              </span>
                              <EditableDescription
                                value={details.description}
                                source={details.description_source}
                                placeholder="No description yet. Describe what one row represents."
                                onSave={(text) => saveDescription(details.name, null, text)}
                              />
                            </div>
                          )}
                          <table className="w-full text-sm">
                            <thead className="sticky top-0 bg-background">
                              <tr className="border-b border-foreground text-left">
                                <th className="px-4 py-3 text-xs font-semibold text-muted-foreground uppercase">
                                  Column
                                </th>
                                <th className="px-4 py-3 text-xs font-semibold text-muted-foreground uppercase">
                                  Type
                                </th>
                                <th className="px-4 py-3 text-xs font-semibold text-muted-foreground uppercase">
                                  Constraints
                                </th>
                                {details && (
                                  <th className="px-4 py-3 text-xs font-semibold text-muted-foreground uppercase min-w-[280px]">
                                    Description (used by the AI)
                                  </th>
                                )}
                              </tr>
                            </thead>
                            <tbody>
                              {columns.map((col) => (
                                <tr
                                  key={col.name}
                                  className="border-b border-foreground/30 hover:bg-foreground/20 transition-colors"
                                >
                                  <td className="px-4 py-3 font-mono text-primary flex items-center gap-2">
                                    {col.is_primary_key && (
                                      <GoKey
                                        className="text-yellow-400"
                                        size={12}
                                      />
                                    )}
                                    {col.foreign_key && (
                                      <GoLink
                                        className="text-blue-400"
                                        size={12}
                                      />
                                    )}
                                    {col.name}
                                  </td>
                                  <td className="px-4 py-3 text-muted-foreground font-mono text-xs">
                                    {col.type}
                                  </td>
                                  <td className="px-4 py-3">
                                    <div className="flex gap-1.5 flex-wrap">
                                      {col.is_primary_key && (
                                        <span className="text-xs bg-yellow-500/10 text-yellow-400 px-1.5 py-0.5 rounded">
                                          PK
                                        </span>
                                      )}
                                      {col.foreign_key && (
                                        <span className="text-xs bg-blue-500/10 text-blue-400 px-1.5 py-0.5 rounded">
                                          FK → {col.foreign_key.referred_table}
                                        </span>
                                      )}
                                      {!col.nullable && (
                                        <span className="text-xs bg-red-500/10 text-red-400 px-1.5 py-0.5 rounded">
                                          NOT NULL
                                        </span>
                                      )}
                                    </div>
                                  </td>
                                  {details && (
                                    <ColumnDescriptionCell
                                      info={details.columns.find((c) => c.name === col.name)}
                                      onSave={(text) => saveDescription(details.name, col.name, text)}
                                    />
                                  )}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          </>
                        )}
                      </>
                    )}

                    {activeTab === "preview" && (
                      <>
                        {loadingPreview ? (
                          <div className="flex items-center justify-center p-8">
                            <FaSpinner
                              className="animate-spin text-accent"
                              size={20}
                            />
                          </div>
                        ) : preview ? (
                          <div className="overflow-auto">
                            <table className="w-full text-sm">
                              <thead className="sticky top-0 bg-background">
                                <tr className="border-b border-foreground">
                                  {preview.columns.map((col) => (
                                    <th
                                      key={col}
                                      className="px-4 py-3 text-xs font-semibold text-muted-foreground uppercase text-left whitespace-nowrap"
                                    >
                                      {col}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {preview.rows.map((row, i) => (
                                  <tr
                                    key={i}
                                    className="border-b border-foreground/30 hover:bg-foreground/20"
                                  >
                                    {preview.columns.map((col) => (
                                      <td
                                        key={col}
                                        className="px-4 py-2 text-primary text-xs font-mono whitespace-nowrap max-w-[200px] truncate"
                                      >
                                        {String(
                                          (row as Record<string, unknown>)[
                                            col
                                          ] ?? ""
                                        )}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                            {preview.rows.length === 0 && (
                              <div className="p-8 text-center text-muted-foreground">
                                No data in this table
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="p-8 text-center text-muted-foreground">
                            Click Preview Data to load
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </>
              ) : (
                <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
                  <GoTable size={32} />
                  <p className="text-sm">Select a table to explore</p>
                </div>
              )}
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
}

function ColumnDescriptionCell({
  info,
  onSave,
}: {
  info: ColumnDetails | undefined;
  onSave: (text: string) => Promise<void>;
}) {
  if (!info) return <td className="px-4 py-3" />;
  const facts = [
    info.text_format,
    info.sample_values.length
      ? `e.g. ${info.sample_values.slice(0, 3).join(", ")}`
      : null,
  ].filter(Boolean);
  return (
    <td className="px-4 py-3 align-top">
      <EditableDescription
        value={info.description}
        source={info.description_source}
        onSave={onSave}
      />
      {facts.length > 0 && (
        <p className="text-[11px] text-muted-foreground mt-1 truncate max-w-[420px]">
          {facts.join(" · ")}
        </p>
      )}
    </td>
  );
}
