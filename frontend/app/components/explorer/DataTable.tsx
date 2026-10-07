"use client";

import React from "react";

import { PiDatabase, PiCheck, PiX } from "react-icons/pi";

interface DataTableProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: { [key: string]: any }[] | null;
  header: { [key: string]: string };
  stickyHeaders?: boolean;
  maxHeight?: string;
}

const DataTable: React.FC<DataTableProps> = ({
  data,
  header,
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

  return (
    <div className={`${containerClassName} chat-animation`} style={containerStyle}>
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

              {Object.keys(header).map((key) => (
                <th
                  key={key}
                  className="min-w-[150px] select-none cursor-default border-b border-r border-foreground_alt px-3 py-3 font-medium"
                >
                  <div className="flex flex-row items-center gap-2 text-secondary">
                    <PiDatabase className="h-4 w-4 opacity-70" />
                    <p className="text-sm font-medium text-primary">
                      {key}
                    </p>
                  </div>
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {data.map((item, rowIndex) => (
              <tr
                key={rowIndex}
                className={
                  rowIndex % 2 === 1 ? "bg-background_alt/50" : ""
                }
              >
                <td className="border-b border-r border-foreground_alt px-3 py-3 text-center text-xs tabular-nums text-secondary">
                  {rowIndex + 1}
                </td>

                {Object.keys(header).map((key, colIndex) => {
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
                            className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-xs ${value
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
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default DataTable;