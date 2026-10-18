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

  // Each tile is as wide as its label and value; tiles wrap on narrow screens.
  return (
    <div className="flex w-full flex-wrap items-start gap-3">
      {view.fields.map((field) => (
        <div
          key={field}
          className="flex w-fit min-w-[8rem] max-w-full flex-col gap-1 rounded-xl border border-foreground_alt bg-background_alt px-4 py-3"
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
