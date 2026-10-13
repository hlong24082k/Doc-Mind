import { authService } from "./services/auth.service.ts";

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
    message?: string
  ) {
    super(message || `API Error: ${status}`);
    this.name = "ApiError";
  }
}

export interface FetchOptions extends Omit<RequestInit, "body"> {
  json?: unknown;
  body?: BodyInit | null;
  query?: Record<string, string | number | boolean | undefined>;
  auth?: boolean;
}

function buildHeaders(options: Pick<FetchOptions, "headers" | "json" | "auth">): Headers {
  const headers = new Headers(options.headers);
  if (options.json !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (options.auth ?? true) {
    const token = localStorage.getItem("access_token");
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }
  return headers;
}

async function throwApiError(response: Response, auth: boolean): Promise<never> {
  if (response.status === 401 && auth) {
    // token hết hạn / không hợp lệ: về trang login
    authService.logout();
    window.location.assign("/login");
  }
  let errorBody: unknown = null;
  try {
    errorBody = await response.json();
  } catch {
    try {
      errorBody = await response.text();
    } catch {
      // ignore
    }
  }
  throw new ApiError(response.status, errorBody, response.statusText);
}

export async function apiFetch<T = unknown>(
  path: string,
  options: FetchOptions = {}
): Promise<T> {
  const { query, headers: customHeaders, auth = true, json, body: rawBody, ...rest } = options;

  const url = new URL(path, typeof window !== "undefined" ? window.location.origin : "http://localhost");
  if (query) {
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null) {
        url.searchParams.append(k, String(v));
      }
    });
  }

  const headers = buildHeaders({ headers: customHeaders, json, auth });
  const bodyToSend: BodyInit | null | undefined = json !== undefined ? JSON.stringify(json) : rawBody;

  const method = (rest.method || "GET").toString().toUpperCase();
  const finalBody = method === "GET" || method === "HEAD" ? undefined : bodyToSend ?? undefined;

  const response = await fetch(url.toString(), {
    ...rest,
    headers,
    body: finalBody,
  });

  if (!response.ok) {
    await throwApiError(response, auth);
  }

  if (response.status === 204) {
    return {} as T;
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as unknown as T;
}

export async function apiFetchBlob(path: string): Promise<Blob> {
  const response = await fetch(path, { headers: buildHeaders({}) });
  if (!response.ok) {
    await throwApiError(response, true);
  }
  return response.blob();
}

function dispatchFrame(frame: string, onEvent: (event: string, data: unknown) => void) {
  let event = "message";
  const data: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue; // ": ping" của sse-starlette
    const idx = line.indexOf(":");
    const field = idx === -1 ? line : line.slice(0, idx);
    let value = idx === -1 ? "" : line.slice(idx + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  if (data.length) onEvent(event, JSON.parse(data.join("\n")));
}

/** POST JSON rồi đọc text/event-stream; field `data` luôn là JSON. */
export async function apiStream(
  path: string,
  opts: {
    json: unknown;
    signal?: AbortSignal;
    onEvent: (event: string, data: unknown) => void;
  }
): Promise<void> {
  const response = await fetch(path, {
    method: "POST",
    headers: buildHeaders({ json: opts.json }),
    body: JSON.stringify(opts.json),
    signal: opts.signal,
  });
  if (!response.ok || !response.body) {
    await throwApiError(response, true);
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? "";
    frames.forEach((frame) => dispatchFrame(frame, opts.onEvent));
  }
  if (buffer.trim()) dispatchFrame(buffer, opts.onEvent);
}
