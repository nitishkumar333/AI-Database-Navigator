"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";

import { IoText } from "react-icons/io5";
import { PiListNumbers } from "react-icons/pi";
import { PiIdentificationBadge } from "react-icons/pi";
import { TbToggleLeft } from "react-icons/tb";
import DataCell from "./components/DataCell";
import { FaBoxArchive } from "react-icons/fa6";

interface DataTableProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: { [key: string]: any }[] | null;
  header: { [key: string]: string };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  setSortOn?: (sort_on: string) => void;
  ascending?: boolean;
  sortOn?: string;
  stickyHeaders?: boolean;
  maxHeight?: string;
  loadingData?: boolean;
}

const DataTable: React.FC<DataTableProps> = ({
  data,
  header,
  setSortOn,
  ascending,
  sortOn,
  stickyHeaders = false,
  maxHeight,
  loadingData,
}) => {
  const [selectedRow, setSelectedRow] = useState<number | null>(null);

  useEffect(() => {
    setSelectedRow(null);
  }, [data, header]);

  if (!data) return null;

  const containerStyle =
    stickyHeaders && maxHeight
      ? {
        maxHeight,
        overflowY: "auto" as const,
      }
      : {};

  const containerClassName = stickyHeaders
    ? `flex flex-col w-full transition-all duration-300 ${loadingData ? "opacity-50" : ""}`
    : `flex flex-col flex-1 min-w-0 min-h-0 overflow-auto w-full transition-all duration-300 ${loadingData ? "opacity-50" : ""}`;

  // Increase height when DataCell is visible
  const dynamicContainerStyle =
    selectedRow !== null
      ? {
        ...containerStyle,
      }
      : containerStyle;

  return (
    <motion.div
      className={containerClassName}
      style={containerStyle}
      animate={dynamicContainerStyle}
      transition={{
        duration: 0.4,
        ease: "easeInOut",
      }}
    >
      {/* Scrollable wrapper */}
      <div className="w-full max-w-full overflow-x-auto">
        {selectedRow === null ? (
          <table className="w-full table-auto whitespace-nowrap border-separate border-spacing-0 overflow-auto no-scrollbar">
            <thead
              className={
                stickyHeaders
                  ? "sticky top-0 z-10 bg-background_alt backdrop-blur"
                  : "bg-background_alt"
              }
            >
              <tr className="text-left text-sm text-secondary">
                <th className="w-12 border-b border-foreground_alt px-3 py-3 text-center font-medium">
                  #
                </th>
                {Object.keys(header).map((key) => {
                  const sortable = !!setSortOn && header[key] !== "uuid";
                  return (
                    <th
                      key={key}
                      className={`min-w-[150px] select-none border-b border-foreground_alt px-3 py-3 font-medium transition-colors ${sortable
                        ? "cursor-pointer hover:bg-foreground_alt"
                        : "cursor-default"
                        }`}
                      onClick={() => sortable && setSortOn(key)}
                    >
                      <div className="flex flex-row items-center gap-2 text-secondary">
                        {header[key] === "text" || header[key] === "text[]" ? (
                          <IoText className="h-4 w-4 opacity-70" />
                        ) : header[key] === "number" ? (
                          <PiListNumbers className="h-4 w-4 opacity-70" />
                        ) : header[key] === "boolean" ? (
                          <TbToggleLeft className="h-4 w-4 opacity-70" />
                        ) : header[key] === "uuid" ? (
                          <PiIdentificationBadge className="h-4 w-4 opacity-70" />
                        ) : header[key] === "object" ||
                          header[key] === "object[]" ? (
                          <FaBoxArchive className="h-4 w-4 opacity-70" />
                        ) : null}
                        <p className="text-sm font-medium text-primary">{key}</p>
                        {sortOn === key && (
                          <span className="text-xs text-primary">
                            {ascending ? "↑" : "↓"}
                          </span>
                        )}
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {data.map((item, rowIndex) => (
                <tr
                  key={rowIndex}
                  className={`group transition-colors hover:bg-foreground_alt ${rowIndex % 2 === 1 ? "bg-background_alt/50" : ""
                    }`}
                >
                  <td className="border-b border-foreground_alt px-3 py-3 text-center text-xs tabular-nums text-secondary">
                    {rowIndex + 1}
                  </td>
                  {Object.keys(header).map((key, colIndex) => {
                    const value = item[key];
                    const isBoolean = typeof value === "boolean";

                    return (
                      <td
                        key={`${rowIndex}-${colIndex}`}
                        onClick={() => setSelectedRow(rowIndex)}
                        className="max-w-[250px] cursor-pointer truncate border-b border-foreground_alt px-3 py-3 text-sm"
                      >
                        {value !== undefined && value !== null ? (
                          typeof value === "object" ? (
                            <span className="rounded-md bg-foreground_alt px-1.5 py-0.5 font-mono text-xs text-primary">
                              {JSON.stringify(value, null, 0)}
                            </span>
                          ) : isBoolean ? (
                            <span
                              className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-xs ${value
                                ? "bg-green-500/10 text-green-400"
                                : "bg-red-500/10 text-red-400"
                                }`}
                            >
                              <span
                                className={`h-1.5 w-1.5 rounded-full ${value ? "bg-green-400" : "bg-red-400"
                                  }`}
                              />
                              {String(value)}
                            </span>
                          ) : (
                            <span className="text-primary">{value}</span>
                          )
                        ) : value === null ? (
                          <span className="text-xs italic text-secondary">
                            null
                          </span>
                        ) : (
                          ""
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <motion.div
            className="relative flex w-full flex-col p-2"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
          >
            <DataCell
              selectedCell={data[selectedRow]}
              onClose={() => setSelectedRow(null)}
            />
          </motion.div>
        )}
      </div>
    </motion.div>
  );
};

export default DataTable;
