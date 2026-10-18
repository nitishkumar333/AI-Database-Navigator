"use client";

import { useEffect, useState } from "react";

export type ChartTheme = {
  series: string[];
  surface: string;
  text: string;
  muted: string;
  grid: string;
};

const FALLBACK: ChartTheme = {
  series: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
  surface: "#ffffff",
  text: "#0f172a",
  muted: "#64748b",
  grid: "#e8edf2",
};

function readTheme(): ChartTheme {
  if (typeof window === "undefined") return FALLBACK;
  const style = getComputedStyle(document.documentElement);
  const raw = (name: string) => style.getPropertyValue(name).trim();
  // Theme tokens are HSL channels ("215 16% 47%"); chart tokens are hex.
  const hsl = (name: string, fallback: string) => (raw(name) ? `hsl(${raw(name)})` : fallback);
  const series = FALLBACK.series.map((fallback, i) => raw(`--chart-${i + 1}`) || fallback);
  return {
    series,
    surface: hsl("--background_alt", FALLBACK.surface),
    text: hsl("--primary", FALLBACK.text),
    muted: hsl("--secondary", FALLBACK.muted),
    grid: hsl("--foreground_alt", FALLBACK.grid),
  };
}

/**
 * Chart colours from the theme's CSS tokens. SVG attributes can't use
 * var(), so the values are read and re-read when the theme switches.
 */
export function useChartTheme(): ChartTheme {
  const [theme, setTheme] = useState<ChartTheme>(FALLBACK);
  useEffect(() => {
    setTheme(readTheme());
    const observer = new MutationObserver(() => setTheme(readTheme()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    });
    return () => observer.disconnect();
  }, []);
  return theme;
}
