import { v4 as uuidv4 } from "uuid";
import { Message, ResultPayload } from "@/app/types/chat";
import { ColumnMeta, ResultSource } from "@/app/types/results";

/**
 * Result payload for an answer, live or stored. The backend sends the column
 * types and the views; an answer without them (never expected) is a table.
 */
export function buildResultPayload(source: ResultSource): ResultPayload {
  const rows = source.rows || [];
  const names = source.columns?.length
    ? source.columns
    : Object.keys(rows[0] || {});
  const columns: ColumnMeta[] = source.column_meta?.length
    ? source.column_meta
    : names.map((name) => ({ name, type: "text", role: null }));
  return {
    type: "result",
    code: { language: "sql", title: "Generated SQL", text: source.generated_sql || "" },
    result: {
      rows,
      columns,
      views: source.views?.length ? source.views : [{ type: "table" }],
      rowCount: source.row_count ?? null,
      truncated: !!source.truncated,
    },
    assumptions: source.assumptions?.trim() || "",
  };
}

export const textMessage = (
  conversationId: string,
  queryId: string,
  text: string
): Message => ({
  type: "text",
  id: uuidv4(),
  conversation_id: conversationId,
  query_id: queryId,
  payload: { type: "response", objects: [{ text }] },
});
