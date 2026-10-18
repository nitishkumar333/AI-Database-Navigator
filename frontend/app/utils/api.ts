import { host } from "../components/host";

export const TOKEN_KEY = "auth_token";

export const getStoredToken = () => localStorage.getItem(TOKEN_KEY) || "";

/**
 * fetch() against the backend. Sends the stored auth token (or `token`) and,
 * when there is a body, sends it as JSON.
 */
export function apiFetch(
  path: string,
  { method, body, token }: { method?: string; body?: unknown; token?: string } = {}
): Promise<Response> {
  const headers: Record<string, string> = {};
  const t = token ?? getStoredToken();
  if (t) headers.Authorization = `Bearer ${t}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  return fetch(`${host}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
