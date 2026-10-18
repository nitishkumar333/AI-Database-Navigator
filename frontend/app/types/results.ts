// A query result as the backend describes it (backend/app/services/display.py).
// The backend decides how a result is shown; the frontend only renders the
// views it is given.

export type ColumnType =
  | "number"
  | "date"
  | "datetime"
  | "boolean"
  | "text"
  | "json"
  | "other";

export type ColumnRole = "image" | "url" | "id" | null;

export type ColumnMeta = {
  name: string;
  type: ColumnType;
  role: ColumnRole;
};

export type ChartType = "bar" | "line" | "pie" | "scatter";

export type TableView = { type: "table" };
export type StatView = { type: "stat"; fields: string[] };
export type CardsView = {
  type: "cards";
  image: string;
  title: string | null;
  fields: string[];
};
export type ChartView = {
  type: ChartType;
  x: string;
  y: string[];
  series: string | null;
};

export type View = TableView | StatView | CardsView | ChartView;

export type Row = Record<string, unknown>;

export type ResultData = {
  rows: Row[];
  columns: ColumnMeta[];
  // The first view is the default; the others can be switched to.
  views: View[];
  // Rows in the full result; null when there were too many to count.
  rowCount: number | null;
  // More rows exist than `rows` holds.
  truncated: boolean;
};

// The result fields of POST /api/query/chat, also stored in a conversation
// message's metadata_json.
export type ResultSource = {
  rows?: Row[];
  columns?: string[];
  column_meta?: ColumnMeta[];
  views?: View[];
  row_count?: number | null;
  truncated?: boolean;
  generated_sql?: string;
};

export const isChartView = (view: View): view is ChartView =>
  view.type === "bar" ||
  view.type === "line" ||
  view.type === "pie" ||
  view.type === "scatter";
