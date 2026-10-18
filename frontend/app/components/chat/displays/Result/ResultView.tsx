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
import { VIEW_HEIGHT } from "./layout";

// The charting library loads only when a chart is shown.
const ResultChart = dynamic(() => import("./ResultChart"), {
  ssr: false,
  loading: () => <Skeleton className="w-full rounded-xl" style={{ height: VIEW_HEIGHT }} />,
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

const RenderView: React.FC<{ view: View; result: ResultData; fixedHeight: boolean }> = ({
  view,
  result,
  fixedHeight,
}) => {
  if (isChartView(view)) return <ResultChart view={view} result={result} />;
  switch (view.type) {
    case "stat":
      return <ResultStat view={view} result={result} />;
    case "cards":
      return <ResultCards view={view} result={result} />;
    default:
      // Next to a chart tab the table has the chart's height, rows stretched
      // to fill it; on its own it fits its rows, scrolling past VIEW_HEIGHT.
      // Heights exclude the box's 1px border.
      return (
        <div
          className="w-full overflow-hidden rounded-xl border border-foreground_alt"
          style={fixedHeight ? { height: VIEW_HEIGHT } : undefined}
        >
          <DataTable
            data={result.rows}
            columns={result.columns}
            stickyHeaders={true}
            fillHeight={fixedHeight ? VIEW_HEIGHT - 2 : undefined}
            maxHeight={`${VIEW_HEIGHT - 2}px`}
          />
        </div>
      );
  }
};

/** A query result in the backend's default view, with its alternatives one click away. */
const ResultView: React.FC<{ result: ResultData }> = ({ result }) => {
  const views = result.views.filter((v) => v.type in VIEW_LABELS);
  const [selected, setSelected] = useState(0);
  const view = views[selected] ?? views[0] ?? { type: "table" };
  const total = result.rowCount;
  const partial = result.truncated || (total !== null && total > result.rows.length);

  return (
    <div className="w-full flex flex-col gap-3">
      {views.length > 1 && (
        <div
          role="tablist"
          aria-label="Result view"
          className="inline-flex w-fit max-w-full flex-wrap gap-1 rounded-lg border border-foreground_alt bg-background_alt p-1 shadow-sm chat-animation"
        >
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
                className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  active
                    ? "bg-accent/15 text-primary ring-1 ring-accent/50"
                    : "text-secondary hover:bg-foreground_alt hover:text-primary"
                }`}
              >
                <Icon className={`h-4 w-4 ${active ? "text-accent" : ""}`} aria-hidden />
                {label}
              </button>
            );
          })}
        </div>
      )}
      <RenderView view={view} result={result} fixedHeight={views.some(isChartView)} />
      {partial && (
        <p className="text-xs text-secondary">
          Showing the first {result.rows.length.toLocaleString()} of{" "}
          {total !== null ? total.toLocaleString() : "more"} rows.
        </p>
      )}
    </div>
  );
};

export default ResultView;
