const API_PREFIX = "/api";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

interface RequestOptions {
  method?: HttpMethod;
  body?: unknown;
}

function extractDetail(data: unknown): unknown {
  if (data && typeof data === "object" && "detail" in (data as Record<string, unknown>)) {
    return (data as Record<string, unknown>).detail;
  }
  return data;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }

  let body: string | undefined;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      method: options.method ?? "GET",
      headers,
      body,
    });
  } catch {
    throw new ApiError(0, null, "Unable to reach the server. Please check your connection.");
  }

  const text = await response.text();
  let data: unknown;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, extractDetail(data));
  }

  return data as T;
}

/** KB-067: authenticated binary download (PDF/Excel). */
export async function downloadAuthenticated(path: string, fallbackFilename: string): Promise<void> {
  const headers: Record<string, string> = { Accept: "*/*" };
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, { method: "GET", headers });
  } catch {
    throw new ApiError(0, null, "Unable to reach the server. Please check your connection.");
  }
  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = extractDetail(await response.json());
    } catch {
      detail = null;
    }
    throw new ApiError(response.status, detail);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = /filename=\"([^\"]+)\"/.exec(disposition);
  const filename = match?.[1] || fallbackFilename;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
