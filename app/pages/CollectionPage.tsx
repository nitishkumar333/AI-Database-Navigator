"use client";

import React, { useContext, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { host } from "../components/host";
import { RouterContext } from "../components/contexts/RouterContext";
import {
  GoTable,
  GoKey,
  GoLink,
  GoArrowLeft,
  GoDatabase,
  GoEye,
} from "react-icons/go";
import { FaSpinner } from "react-icons/fa";
import { useSearchParams } from "next/navigation";
import { Separator } from "@/components/ui/separator";

type TableInfo = {
  name: string;
  column_count: number;
};

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

type PreviewData = {
  columns: string[];
  rows: Record<string, unknown>[];
};

export default function CollectionPage() {
  const searchParams = useSearchParams();
  const collectionName = searchParams.get("collection") || "";
  const { changePage } = useContext(RouterContext);

  const [tables, setTables] = useState<TableInfo[]>([]);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [columns, setColumns] = useState<ColumnInfo[]>([]);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingColumns, setLoadingColumns] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [activeTab, setActiveTab] = useState<"columns" | "preview">("columns");

  // Extract connection name — get auth token
  const connName = collectionName.split(" (")[0];
  const getToken = () => localStorage.getItem("auth_token") || "";

  // Find connection ID
  const [connId, setConnId] = useState<number | null>(null);

  useEffect(() => {
    findConnection();
  }, [connName]);

  const findConnection = async () => {
    try {
      const response = await fetch(`${host}/api/connections`, {
        headers: {
          Authorization: `Bearer ${getToken()}`,
          "Content-Type": "application/json",
        },
      });
      if (response.ok) {
        const conns = await response.json();
        const match = conns.find(
          (c: { name: string }) => c.name === connName
        );
        if (match) {
          setConnId(match.id);
          loadTables(match.id);
        }
      }
    } catch (e) {
      console.error("Failed to find connection:", e);
    }
  };

  const loadTables = async (cId: number) => {
    setLoading(true);
    try {
      const response = await fetch(`${host}/api/schema/${cId}/tables`, {
        headers: {
          Authorization: `Bearer ${getToken()}`,
          "Content-Type": "application/json",
        },
      });
      if (response.ok) {
        const data = await response.json();
        setTables(data);
      }
    } catch (e) {
      console.error("Failed to load tables:", e);
    }
    setLoading(false);
  };

  const loadColumns = async (tableName: string) => {
    if (!connId) return;
    setLoadingColumns(true);
    setSelectedTable(tableName);
    setActiveTab("columns");
    setPreview(null);
    try {
      const response = await fetch(
        `${host}/api/schema/${connId}/tables/${tableName}/columns`,
        {
          headers: {
            Authorization: `Bearer ${getToken()}`,
            "Content-Type": "application/json",
          },
        }
      );
      if (response.ok) {
        const data = await response.json();
        setColumns(data);
      }
    } catch (e) {
      console.error("Failed to load columns:", e);
    }
    setLoadingColumns(false);
  };

  const loadPreview = async (tableName: string) => {
    if (!connId) return;
    setLoadingPreview(true);
    setActiveTab("preview");
    try {
      const response = await fetch(
        `${host}/api/schema/${connId}/tables/${tableName}/preview`,
        {
          headers: {
            Authorization: `Bearer ${getToken()}`,
            "Content-Type": "application/json",
          },
        }
      );
      if (response.ok) {
        const data = await response.json();
        setPreview(data);
      }
    } catch (e) {
      console.error("Failed to load preview:", e);
    }
    setLoadingPreview(false);
  };

  return (
    <div className="flex flex-col w-full h-screen overflow-hidden p-2 lg:p-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-4 w-full h-full"
      >
        {/* Header */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <button
            onClick={() => changePage("data", {}, true)}
            className="text-muted-foreground hover:text-primary transition-colors"
          >
            <GoArrowLeft size={20} />
          </button>
          <GoDatabase className="text-accent" size={20} />
          <div>
            <h1 className="text-xl font-bold text-primary">{connName}</h1>
            <p className="text-xs text-muted-foreground">
              {tables.length} tables found
            </p>
          </div>
        </div>

        <Separator />

        {loading ? (
          <div className="flex items-center justify-center flex-1">
            <FaSpinner className="animate-spin text-accent" size={32} />
          </div>
        ) : (
          <div className="flex gap-4 flex-1 min-h-0 overflow-hidden">
            {/* Table List */}
            <div className="w-64 flex-shrink-0 border border-foreground rounded-xl overflow-y-auto">
              <div className="p-3 border-b border-foreground">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Tables
                </p>
              </div>
              {tables.map((table) => (
                <button
                  key={table.name}
                  onClick={() => loadColumns(table.name)}
                  className={`w-full text-left px-4 py-3 text-sm border-b border-foreground/50 hover:bg-foreground/30 transition-colors flex items-center justify-between ${
                    selectedTable === table.name
                      ? "bg-accent/10 text-accent border-l-2 border-l-accent"
                      : "text-primary"
                  }`}
                >
                  <span className="flex items-center gap-2 truncate">
                    <GoTable size={14} />
                    {table.name}
                  </span>
                  <span className="text-xs text-muted-foreground">
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
                                </tr>
                              ))}
                            </tbody>
                          </table>
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
