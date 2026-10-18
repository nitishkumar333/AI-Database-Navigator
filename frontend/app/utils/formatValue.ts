import { ColumnMeta, ColumnType } from "@/app/types/results";

const NUMBER = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const COMPACT = new Intl.NumberFormat(undefined, {
  notation: "compact",
  maximumFractionDigits: 1,
});
const DATE = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });
const DATETIME = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

/** A finite number from a result value, or null. */
export function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "" || typeof value === "boolean")
    return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * Milliseconds for a date value. Plain "YYYY-MM-DD" dates are read as local
 * dates, so they don't shift a day in timezones west of UTC.
 */
export function toTime(value: unknown): number | null {
  if (typeof value !== "string" && typeof value !== "number") return null;
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [y, m, d] = value.split("-").map(Number);
    return new Date(y, m - 1, d).getTime();
  }
  const t = new Date(value).getTime();
  return Number.isFinite(t) ? t : null;
}

export function formatNumber(value: unknown, compact = false): string {
  const n = toNumber(value);
  if (n === null) return value === null || value === undefined ? "—" : String(value);
  return (compact && Math.abs(n) >= 10_000 ? COMPACT : NUMBER).format(n);
}

/** A result value as display text, by its column type. */
export function formatValue(value: unknown, type: ColumnType = "text"): string {
  if (value === null || value === undefined) return "—";
  switch (type) {
    case "number":
      return formatNumber(value);
    case "date":
    case "datetime": {
      const t = toTime(value);
      if (t === null) return String(value);
      return (type === "date" ? DATE : DATETIME).format(t);
    }
    case "boolean":
      return value ? "Yes" : "No";
    default:
      return typeof value === "object" ? JSON.stringify(value) : String(value);
  }
}

/** "unit_price" -> "Unit price". */
export function columnLabel(name: string): string {
  const spaced = name.replace(/[_-]+/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").trim();
  return spaced ? spaced[0].toUpperCase() + spaced.slice(1) : name;
}

export function columnMap(columns: ColumnMeta[]): Record<string, ColumnMeta> {
  return Object.fromEntries(columns.map((c) => [c.name, c]));
}

/** Only http(s) URLs are ever put in src/href. */
export function safeUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const url = value.trim();
  return /^https?:\/\//i.test(url) ? url : null;
}
