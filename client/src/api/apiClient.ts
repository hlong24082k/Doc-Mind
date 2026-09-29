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

  const headers = new Headers(customHeaders);

  let bodyToSend: BodyInit | null | undefined = rawBody;
  if (json !== undefined) {
    bodyToSend = JSON.stringify(json);
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  }

  if (auth) {
    const token = localStorage.getItem("access_token");
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const method = (rest.method || "GET").toString().toUpperCase();
  const finalBody = method === "GET" || method === "HEAD" ? undefined : bodyToSend ?? undefined;

  const response = await fetch(url.toString(), {
    ...rest,
    headers,
    body: finalBody,
  });

  if (!response.ok) {
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

  if (response.status === 204) {
    return {} as T;
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as unknown as T;
}
