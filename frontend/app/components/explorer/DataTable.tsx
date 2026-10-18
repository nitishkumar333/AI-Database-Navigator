"use client";

import React from "react";
import { motion, Variants } from "framer-motion";

import { PiDatabase, PiCheck, PiX } from "react-icons/pi";

// Rows fade in one after another once the table is on screen. Later rows
// share the last delay so long tables don't take ages to appear.
const MAX_STAGGERED_ROWS = 15;

const rowVariants: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: (rowIndex: number) => ({
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.25,
      ease: "easeOut",
      delay: 0.2 + Math.min(rowIndex, MAX_STAGGERED_ROWS) * 0.1,
    },
  }),
};

interface DataTableProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: { [key: string]: any }[] | null;
  stickyHeaders?: boolean;
  maxHeight?: string;
}

const DataTable: React.FC<DataTableProps> = ({
  data,
  stickyHeaders = false,
  maxHeight,
}) => {
  if (!data) return null;

  const containerStyle =
    stickyHeaders && maxHeight
      ? {
          maxHeight,
          overflowY: "auto" as const,
        }
      : {};

  const containerClassName = stickyHeaders
    ? "flex flex-col w-full"
    : "flex flex-col flex-1 min-w-0 min-h-0 overflow-auto w-full";

  const columns = Object.keys(data[0] || {});
  const rowCount = data.length;
  const columnCount = columns.length;

  return (
    <div
      className={`flex flex-col w-full ${stickyHeaders ? "" : "flex-1 min-w-0 min-h-0"} chat-animation-fast`}
    >
      {/* Outside the scroll area so it stays visible */}
      <p className="px-3 pb-3 text-xs text-secondary">
        {rowCount} {rowCount === 1 ? "row" : "rows"} · {columnCount}{" "}
        {columnCount === 1 ? "column" : "columns"}
      </p>
      <div className={containerClassName} style={containerStyle}>
        {/* Scrollable wrapper */}
        <div className="w-full max-w-full overflow-x-auto">
          <table className="w-full table-auto whitespace-nowrap border-separate border-spacing-0 overflow-auto no-scrollbar">
            <thead
              className={
                stickyHeaders
                  ? "sticky top-0 z-10 bg-background_alt backdrop-blur"
                  : "bg-background_alt"
              }
            >
              <tr className="text-left text-sm text-secondary">
                <th className="w-12 border-b border-r border-foreground_alt px-3 py-3 text-center font-medium">
                  #
                </th>

                {columns.map((key) => (
                  <th
                    key={key}
                    className="min-w-[150px] select-none cursor-default border-b border-r border-foreground_alt px-3 py-3 font-medium"
                  >
                    <div className="flex flex-row items-center gap-2 text-secondary">
                      <PiDatabase className="h-4 w-4 opacity-70" />
                      <p className="text-sm font-medium text-primary">{key}</p>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>

            <motion.tbody
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, amount: 0.1 }}
            >
              {data.map((item, rowIndex) => (
                <motion.tr
                  key={rowIndex}
                  custom={rowIndex}
                  variants={rowVariants}
                  className={rowIndex % 2 === 1 ? "bg-background_alt/50" : ""}
                >
                  <td className="border-b border-r border-foreground_alt px-3 py-3 text-center text-xs tabular-nums text-secondary">
                    {rowIndex + 1}
                  </td>

                  {columns.map((key, colIndex) => {
                    const value = item[key];
                    const isBoolean = typeof value === "boolean";

                    return (
                      <td
                        key={`${rowIndex}-${colIndex}`}
                        className="max-w-[250px] truncate border-b border-r border-foreground_alt px-3 py-3 text-sm"
                      >
                        {value !== undefined && value !== null ? (
                          typeof value === "object" ? (
                            <span className="rounded-md bg-foreground_alt px-1.5 py-0.5 font-mono text-xs text-primary">
                              {JSON.stringify(value, null, 0)}
                            </span>
                          ) : isBoolean ? (
                            <span
                              className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-xs ${
                                value
                                  ? "bg-green-500/10 text-green-400"
                                  : "bg-red-500/10 text-red-400"
                              }`}
                            >
                              {value ? (
                                <PiCheck className="h-3 w-3" />
                              ) : (
                                <PiX className="h-3 w-3" />
                              )}
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
                </motion.tr>
              ))}
            </motion.tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default DataTable;
