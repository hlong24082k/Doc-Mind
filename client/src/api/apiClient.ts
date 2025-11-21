import { authService } from "@/api/services/auth.service";

/* -------------------------------------------------------------------------- */
/*                                Custom Error                                */
/* -------------------------------------------------------------------------- */

/**
 * Custom error class for API responses.
 * Contains the response status and the parsed error body.
 */
export class ApiError extends Error {
  constructor(
    public status: number,
    public body: any,
    message?: string
  ) {
    super(message || `API Error: ${status}`);
    this.name = "ApiError";
  }
}

/* -------------------------------------------------------------------------- */
/*                                    Types                                   */
/* -------------------------------------------------------------------------- */

interface FetchOptions extends Omit<RequestInit, "body"> {
  /**
   * Plain object that will be stringified as JSON.
   * For other body types (FormData, Blob, etc.), use the standard `body` property.
   */
  json?: Record<string, unknown>;
  /** The raw body for the request (e.g., FormData). Use `json` for objects. */
  body?: BodyInit | null;
  /** Query string parameters appended to URL. */
  query?: Record<string, string | number | boolean | undefined>;
  /** Whether to attach the Authorization token (default: true). */
  auth?: boolean;
}

/* -------------------------------------------------------------------------- */
/*                              Internal Helpers                              */
/* -------------------------------------------------------------------------- */

/** Builds a full URL, appending query parameters from a record. */
function buildUrl(path: string, query?: FetchOptions["query"]): string {
  let url: URL;
  try {
    url = new URL(path);
  } catch (err) {
    // If `path` is relative, use current origin as base.
    url = new URL(path, typeof window !== "undefined" ? window.location.origin : "http://localhost");
  }
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) {
        url.searchParams.append(key, String(value));
      }
    }
  }
  return url.toString();
}

/** Retrieves the access token from localStorage. */
function getAccessToken(): string | null {
  return localStorage.getItem("access_token");
}

/** Normalize HeadersInit into a plain object of string values */
function normalizeHeaders(h?: HeadersInit): Record<string, string> {
  const out: Record<string, string> = {};
  if (!h) return out;
  if (h instanceof Headers) {
    h.forEach((v, k) => (out[k] = v));
    return out;
  }
  if (Array.isArray(h)) {
    for (const [k, v] of h) out[k] = String(v);
    return out;
  }
  for (const k of Object.keys(h as Record<string, unknown>)) {
    const val = (h as Record<string, unknown>)[k];
    if (val !== undefined && val !== null) out[k] = String(val);
  }
  return out;
}

/* -------------------------------------------------------------------------- */
/*                             Core Fetch Logic                               */
/* -------------------------------------------------------------------------- */

async function fetchWithAuthRetry<T>(
  path: string,
  options: FetchOptions,
  isRetry = false
): Promise<T> {
  const { query, headers: customHeaders, auth = true, json, body: rawBody, ...rest } = options;

  const url = buildUrl(path, query);
  const token = auth ? getAccessToken() : null;

  // Prepare body
  let body: BodyInit | null = null;
  if (json !== undefined) {
    body = JSON.stringify(json);
  } else if (rawBody !== undefined) {
    body = rawBody;
  }

  // Normalize and prepare headers
  const headersObj = normalizeHeaders(customHeaders);

  // If the body is FormData, do not set Content-Type (browser will add the boundary)
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
  if (isFormData) {
    // Ensure no Content-Type is set so browser can set boundary
    delete headersObj["content-type"];
  } else if (json !== undefined) {
    if (!Object.keys(headersObj).some(k => k.toLowerCase() === "content-type")) {
      headersObj["Content-Type"] = "application/json";
    }
  }

  // Attach Authorization if needed
  if (auth && token) {
    if (!Object.keys(headersObj).some(k => k.toLowerCase() === "authorization")) {
      headersObj["Authorization"] = `Bearer ${token}`;
    }
  }

  const method = (rest.method || "GET").toString().toUpperCase();
  const bodyToSend = method === "GET" || method === "HEAD" ? undefined : body ?? undefined;

  const response = await fetch(url, {
    ...rest,
    headers: headersObj,
    body: bodyToSend,
  });

  // Handle expired access token with a single retry
  if (response.status === 401 && auth && !isRetry) {
    console.warn("[apiFetch] Access token expired, attempting refresh...");
    const newToken = await authService.refreshToken();
    if (newToken) {
      // The authService already stored the token, so we just retry the request.
      return fetchWithAuthRetry<T>(path, options, true);
    } else {
      // Refresh failed, propagate a clear error.
      throw new ApiError(401, null, "Unauthorized: Token refresh failed");
    }
  }

  // Handle non-successful responses
  if (!response.ok) {
    let errorBody: any = null;
    try {
      errorBody = await response.json();
    } catch {
      try {
        errorBody = await response.text();
      } catch {
        // Could not parse error body
      }
    }
    throw new ApiError(response.status, errorBody, response.statusText);
  }

  // Handle no-content responses
  if (response.status === 204) {
    return {} as T;
  }

  // Auto-detect and parse JSON or return text
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  } else {
    return (await response.text()) as unknown as T;
  }
}

/* -------------------------------------------------------------------------- */
/*                             Public API Wrapper                             */
/* -------------------------------------------------------------------------- */

/**
 * Main API entry point for all requests.
 * Handles auth, token refresh, and response parsing.
 *
 * @param path The URL path for the request.
 * @param options Configuration for the fetch call.
 * @returns The parsed response data.
 */
export async function apiFetch<T = unknown>(
  path: string,
  options: FetchOptions = {}
): Promise<T> {
  return fetchWithAuthRetry<T>(path, options);
}
