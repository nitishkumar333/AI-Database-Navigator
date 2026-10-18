"use client";

import React, { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartView, ResultData } from "@/app/types/results";
import { columnLabel, formatNumber } from "@/app/utils/formatValue";
import { buildChartData, X_KEY } from "./chartData";
import { useChartTheme } from "./useChartTheme";
import { VIEW_HEIGHT } from "./layout";

const BAR_ROW = 28; // px per category in a horizontal bar chart
const MAX_LABEL = 18;

const shorten = (value: unknown) => {
  const text = String(value ?? "");
  return text.length > MAX_LABEL ? text.slice(0, MAX_LABEL - 1) + "…" : text;
};

/** A chart the backend validated against the rows (see display.py). */
const ResultChart: React.FC<{ view: ChartView; result: ResultData }> = ({ view, result }) => {
  const theme = useChartTheme();
  const { points, series } = useMemo(
    () => buildChartData(view, result.rows, result.columns),
    [view, result.rows, result.columns]
  );
  const color = (i: number) => theme.series[i % theme.series.length];
  // Series names: the measure for a plain chart, the series value otherwise.
  const seriesName = (name: string) => (view.series ? name : columnLabel(name));
  const showLegend = series.length > 1 || view.type === "pie";
  const title = `${view.y.map(columnLabel).join(", ")} by ${columnLabel(view.x)}${
    view.series ? ` and ${columnLabel(view.series)}` : ""
  }`;

  const axisProps = {
    stroke: theme.grid,
    tick: { fill: theme.muted, fontSize: 12 },
    tickLine: false,
  };
  const valueAxis = {
    ...axisProps,
    axisLine: false,
    tickFormatter: (v: number) => formatNumber(v, true),
    width: 56,
  };
  const tooltip = (
    <Tooltip
      cursor={{ fill: theme.grid, opacity: 0.4, stroke: theme.grid }}
      formatter={(value: unknown, name: unknown) => [formatNumber(value), String(name)]}
      contentStyle={{
        background: theme.surface,
        border: `1px solid ${theme.grid}`,
        borderRadius: 8,
        color: theme.text,
        fontSize: 12,
      }}
      labelStyle={{ color: theme.text, fontWeight: 600 }}
      itemStyle={{ color: theme.text }}
    />
  );
  const legend = showLegend ? (
    <Legend
      iconType="circle"
      iconSize={8}
      wrapperStyle={{ fontSize: 12, color: theme.muted, paddingTop: 8 }}
    />
  ) : null;

  let chart: React.ReactElement;
  // The plot fills the view; a horizontal bar chart with many categories is
  // taller and scrolls inside it.
  let plotHeight: number | null = null;

  if (view.type === "bar") {
    const longLabels = points.some((p) => String(p[X_KEY] ?? "").length > 10);
    const horizontal = points.length > 8 || (longLabels && points.length > 4);
    if (horizontal) {
      const needed = points.length * BAR_ROW * Math.max(1, series.length / 2) + 60;
      if (needed > VIEW_HEIGHT - 80) plotHeight = needed;
    }
    chart = (
      <BarChart
        data={points}
        layout={horizontal ? "vertical" : "horizontal"}
        margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
        barCategoryGap="20%"
        barGap={2}
      >
        <CartesianGrid stroke={theme.grid} vertical={!horizontal} horizontal={horizontal ? false : true} />
        {horizontal ? (
          <>
            <XAxis type="number" {...valueAxis} />
            <YAxis
              type="category"
              dataKey={X_KEY}
              {...axisProps}
              width={130}
              tickFormatter={shorten}
              interval={0}
            />
          </>
        ) : (
          <>
            <XAxis dataKey={X_KEY} {...axisProps} tickFormatter={shorten} />
            <YAxis {...valueAxis} />
          </>
        )}
        {tooltip}
        {legend}
        {series.map((s, i) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={seriesName(s.name)}
            fill={color(i)}
            stroke={theme.surface}
            strokeWidth={1}
            radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
            maxBarSize={48}
          />
        ))}
      </BarChart>
    );
  } else if (view.type === "line") {
    const dots = points.length <= 30;
    chart = (
      <LineChart data={points} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid stroke={theme.grid} vertical={false} />
        <XAxis dataKey={X_KEY} {...axisProps} tickFormatter={shorten} minTickGap={16} />
        <YAxis {...valueAxis} />
        {tooltip}
        {legend}
        {series.map((s, i) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={seriesName(s.name)}
            stroke={color(i)}
            strokeWidth={2}
            dot={dots ? { r: 3, strokeWidth: 0, fill: color(i) } : false}
            activeDot={{ r: 5, stroke: theme.surface, strokeWidth: 2 }}
            connectNulls
          />
        ))}
      </LineChart>
    );
  } else if (view.type === "pie") {
    const key = series[0]?.key ?? "y0";
    chart = (
      <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        {tooltip}
        {legend}
        <Pie
          data={points}
          dataKey={key}
          nameKey={X_KEY}
          innerRadius="55%"
          outerRadius="85%"
          stroke={theme.surface}
          strokeWidth={2}
          isAnimationActive
          animationBegin={100}
        >
          {points.map((_, i) => (
            <Cell key={i} fill={color(i)} />
          ))}
        </Pie>
      </PieChart>
    );
  } else {
    chart = (
      <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid stroke={theme.grid} />
        <XAxis
          type="number"
          dataKey={X_KEY}
          name={columnLabel(view.x)}
          {...axisProps}
          tickFormatter={(v: number) => formatNumber(v, true)}
          domain={["auto", "auto"]}
        />
        <YAxis type="number" dataKey="y" name={columnLabel(view.y[0])} {...valueAxis} domain={["auto", "auto"]} />
        {tooltip}
        {legend}
        {series.map((s, i) => (
          <Scatter
            key={s.key}
            name={seriesName(s.name)}
            data={points
              .filter((p) => p[s.key] !== undefined && p[s.key] !== null)
              .map((p) => ({ [X_KEY]: p[X_KEY], y: p[s.key] }))}
            fill={color(i)}
            stroke={theme.surface}
            strokeWidth={1}
          />
        ))}
      </ScatterChart>
    );
  }

  return (
    <figure
      className="relative flex w-full flex-col overflow-hidden rounded-xl border border-foreground_alt bg-background_alt p-4"
      style={{ height: VIEW_HEIGHT }}
    >
      {view.type === "pie" && (
        // A pie leaves most of the frame empty: a dot mesh fading out from
        // the centre, with a faint wash of the first slice colour.
        <div aria-hidden className="pointer-events-none absolute inset-0">
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: `radial-gradient(circle, ${theme.muted} 1px, transparent 1.5px)`,
              backgroundSize: "18px 18px",
              backgroundPosition: "center",
              opacity: 0.15,
              maskImage: "radial-gradient(ellipse at center, black 30%, transparent 75%)",
              WebkitMaskImage: "radial-gradient(ellipse at center, black 30%, transparent 75%)",
            }}
          />
        </div>
      )}
      <figcaption className="relative mb-3 truncate text-sm font-medium text-primary">{title}</figcaption>
      <div className="relative min-h-0 flex-1 overflow-y-auto">
        <div
          style={{ width: "100%", height: plotHeight ?? "100%" }}
          role="img"
          aria-label={`${view.type} chart: ${title}`}
        >
          <ResponsiveContainer width="100%" height="100%">
            {chart}
          </ResponsiveContainer>
        </div>
      </div>
    </figure>
  );
};

export default ResultChart;
