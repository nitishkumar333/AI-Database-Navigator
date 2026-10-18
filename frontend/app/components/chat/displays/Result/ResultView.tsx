"use client";

import React, { useState } from "react";
import { IconType } from "react-icons";
import {
  PiChartBar,
  PiChartLine,
  PiChartPieSlice,
  PiChartScatter,
  PiHash,
  PiSquaresFour,
  PiTable,
} from "react-icons/pi";
import { isChartView, ResultData, View } from "@/app/types/results";
import DataTable from "@/app/components/explorer/DataTable";
import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";
import ResultCards from "./ResultCards";
import ResultStat from "./ResultStat";

// The charting library loads only when a chart is shown.
const ResultChart = dynamic(() => import("./ResultChart"), {
  ssr: false,
  loading: () => <Skeleton className="w-full h-[360px] rounded-xl" />,
});

const VIEW_LABELS: Record<View["type"], [string, IconType]> = {
  table: ["Table", PiTable],
  stat: ["Summary", PiHash],
  cards: ["Cards", PiSquaresFour],
  bar: ["Bar chart", PiChartBar],
  line: ["Line chart", PiChartLine],
  pie: ["Pie chart", PiChartPieSlice],
  scatter: ["Scatter", PiChartScatter],
};

const RenderView: React.FC<{ view: View; result: ResultData }> = ({ view, result }) => {
  if (isChartView(view)) return <ResultChart view={view} result={result} />;
  switch (view.type) {
    case "stat":
      return <ResultStat view={view} result={result} />;
    case "cards":
      return <ResultCards view={view} result={result} />;
    default:
      return (
        <DataTable
          data={result.rows}
          columns={result.columns}
          totalRows={result.rowCount}
          truncated={result.truncated}
          stickyHeaders={true}
          maxHeight="40vh"
        />
      );
  }
};

/** A query result in the backend's default view, with its alternatives one click away. */
const ResultView: React.FC<{ result: ResultData }> = ({ result }) => {
  const views = result.views.filter((v) => v.type in VIEW_LABELS);
  const [selected, setSelected] = useState(0);
  const view = views[selected] ?? views[0] ?? { type: "table" };

  return (
    <div className="w-full flex flex-col gap-3">
      {views.length > 1 && (
        <div role="tablist" aria-label="Result view" className="flex flex-wrap gap-1">
          {views.map((v, i) => {
            const [label, Icon] = VIEW_LABELS[v.type];
            const active = i === selected;
            return (
              <button
                key={`${v.type}-${i}`}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setSelected(i)}
                className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition-colors ${
                  active
                    ? "bg-foreground_alt text-primary"
                    : "text-secondary hover:bg-foreground_alt/60 hover:text-primary"
                }`}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden />
                {label}
              </button>
            );
          })}
        </div>
      )}
      <RenderView view={view} result={result} />
    </div>
  );
};

export default ResultView;
