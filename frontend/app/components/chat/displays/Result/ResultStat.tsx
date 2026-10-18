"use client";

import React from "react";
import { ResultData, StatView } from "@/app/types/results";
import { columnLabel, columnMap } from "@/app/utils/formatValue";
import ResultValue from "./ResultValue";

/** The values of a one-row result as headline tiles. */
const ResultStat: React.FC<{ view: StatView; result: ResultData }> = ({ view, result }) => {
  const row = result.rows[0] || {};
  const columns = columnMap(result.columns);
  const single = view.fields.length === 1;

  return (
    <div
      className={`grid w-full gap-3 ${
        single ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
      }`}
    >
      {view.fields.map((field) => (
        <div
          key={field}
          className="flex flex-col gap-1 rounded-xl border border-foreground_alt bg-background_alt p-4 min-w-0"
        >
          <span className="text-xs uppercase tracking-wide text-secondary truncate">
            {columnLabel(field)}
          </span>
          <ResultValue
            value={row[field]}
            column={columns[field]}
            className={`font-semibold text-primary tabular-nums break-words ${
              single ? "text-3xl" : "text-2xl"
            }`}
          />
        </div>
      ))}
    </div>
  );
};

export default ResultStat;
