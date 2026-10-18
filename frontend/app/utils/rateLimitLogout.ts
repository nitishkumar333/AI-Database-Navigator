// Signs the user out when the API's own rate limit refuses a request.
//
// Importing this module wraps window.fetch once. A 429 carrying the
// "X-Rate-Limit: api" header (our limiter; a 429 passed on from the LLM
// provider has no such header) dispatches RATE_LIMIT_LOGOUT_EVENT with the
// seconds until the limit allows requests again; AuthProvider listens, signs
// the user out and the login page explains why. Login, register and guest
// login are skipped: nobody is signed in yet, and their forms show the error.
// Responses are returned unchanged.

import { host } from "../components/host";

export const RATE_LIMIT_LOGOUT_EVENT = "sqlnav:rate-limit-logout";

export type RateLimitLogoutDetail = { seconds: number | null };

const NOT_SIGNED_IN_YET = ["/api/auth/login", "/api/auth/register", "/api/auth/guest"];

/** Seconds until the request may be retried, from Retry-After or the message. */
export async function retryAfterSeconds(response: Response): Promise<number | null> {
  const header = Number(response.headers.get("retry-after"));
  if (Number.isFinite(header) && header > 0) return Math.ceil(header);
  try {
    const data = await response.clone().json();
    const match = String(data?.detail ?? "").match(/(\d+)\s*second/);
    if (match) return Number(match[1]);
  } catch {
    // not JSON
  }
  return null;
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function install() {
  const w = window as typeof window & { __rateLimitLogout?: boolean };
  if (w.__rateLimitLogout) return; // once, even with hot reload
  w.__rateLimitLogout = true;
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const response = await originalFetch(input, init);
    if (response.status === 429 && response.headers.get("x-rate-limit") === "api") {
      const path = requestUrl(input).replace(host, "");
      if (path.startsWith("/api/") && !NOT_SIGNED_IN_YET.some((p) => path.startsWith(p))) {
        const seconds = await retryAfterSeconds(response);
        window.dispatchEvent(
          new CustomEvent<RateLimitLogoutDetail>(RATE_LIMIT_LOGOUT_EVENT, {
            detail: { seconds },
          })
        );
      }
    }
    return response;
  };
}

if (typeof window !== "undefined") install();
