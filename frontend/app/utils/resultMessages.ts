import { v4 as uuidv4 } from "uuid";
import { Message, ResultPayload } from "@/app/types/chat";
import { detectProductData, mapRowsToProducts } from "./detectProductdata";

/**
 * Result payload for query rows: product cards when the rows look like a
 * product catalogue, a table otherwise. `limits` caps the rows kept for each
 * kind (no product limit keeps every row).
 */
export function buildResultPayload(
  rows: Record<string, unknown>[],
  columns: string[] | undefined,
  sql: string | undefined,
  limits: { product?: number; table: number }
): ResultPayload {
  const code = { language: "sql", title: "Generated SQL", text: sql || "" };
  const { isProduct, fieldMapping } = detectProductData(rows, columns);
  if (isProduct) {
    return {
      type: "product",
      code,
      objects: mapRowsToProducts(rows.slice(0, limits.product), fieldMapping),
    };
  }
  return { type: "table", code, objects: rows.slice(0, limits.table) };
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
