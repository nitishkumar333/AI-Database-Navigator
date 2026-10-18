import { ChartView, ColumnMeta, Row } from "@/app/types/results";
import { formatValue, toNumber, toTime } from "@/app/utils/formatValue";

export const X_KEY = "__x";

export type Series = { key: string; name: string };

export type ChartData = {
  points: Record<string, unknown>[];
  series: Series[];
};

const xOrder = (value: unknown, column?: ColumnMeta): number | null => {
  if (!column) return null;
  if (column.type === "number") return toNumber(value);
  if (column.type === "date" || column.type === "datetime") return toTime(value);
  return null;
};

/**
 * Recharts points for a chart view. Each point has the formatted x label
 * under X_KEY and one number per series. With `series`, rows in long format
 * (one per x and series value) are pivoted into one point per x. Line charts
 * over dates or numbers are sorted by x; other charts keep the SQL order.
 */
export function buildChartData(view: ChartView, rows: Row[], columns: ColumnMeta[]): ChartData {
  const xColumn = columns.find((c) => c.name === view.x);
  const sortable = view.type === "line" || view.type === "scatter";
  let ordered = rows;
  if (sortable && xColumn && ["number", "date", "datetime"].includes(xColumn.type)) {
    ordered = [...rows].sort(
      (a, b) =>
        (xOrder(a[view.x], xColumn) ?? Infinity) - (xOrder(b[view.x], xColumn) ?? Infinity)
    );
  }
  const label = (value: unknown) =>
    view.type === "scatter" ? toNumber(value) : formatValue(value, xColumn?.type);

  if (!view.series) {
    const series = view.y.map((name, i) => ({ key: `y${i}`, name }));
    const points = ordered.map((row) => {
      const point: Record<string, unknown> = { [X_KEY]: label(row[view.x]) };
      view.y.forEach((name, i) => (point[`y${i}`] = toNumber(row[name])));
      return point;
    });
    return { points, series };
  }

  const seriesName = view.series;
  const measure = view.y[0];
  const seriesKeys = new Map<string, string>();
  const byX = new Map<string, Record<string, unknown>>();
  for (const row of ordered) {
    const name = formatValue(row[seriesName]);
    if (!seriesKeys.has(name)) seriesKeys.set(name, `s${seriesKeys.size}`);
    const key = seriesKeys.get(name)!;
    if (view.type === "scatter") {
      // Scatter series are separate point sets, not pivoted by x.
      byX.set(`${byX.size}`, { [X_KEY]: label(row[view.x]), [key]: toNumber(row[measure]) });
      continue;
    }
    const x = String(label(row[view.x]));
    const point = byX.get(x) ?? { [X_KEY]: label(row[view.x]) };
    point[key] = toNumber(row[measure]);
    byX.set(x, point);
  }
  return {
    points: Array.from(byX.values()),
    series: Array.from(seriesKeys, ([name, key]) => ({ key, name })),
  };
}
