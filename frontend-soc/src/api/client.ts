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

export async function request<T>(
  path: string,
  options: { method?: string; body?: unknown } = {}
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
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
    throw new ApiError(0, null, "Unable to reach the server.");
  }
  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    const detail =
      data && typeof data === "object" && "detail" in (data as object)
        ? (data as { detail: unknown }).detail
        : data;
    throw new ApiError(response.status, detail);
  }
  return data as T;
}

/** Authenticated binary download (PDF/Excel/forensics) — same contract as Admin portal. */
export async function downloadAuthenticated(path: string, fallbackFilename: string): Promise<void> {
  const headers: Record<string, string> = { Accept: "*/*" };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, { method: "GET", headers });
  } catch {
    throw new ApiError(0, null, "Unable to reach the server.");
  }
  if (!response.ok) {
    let detail: unknown = null;
    try {
      const j = await response.json();
      detail =
        j && typeof j === "object" && "detail" in (j as object)
          ? (j as { detail: unknown }).detail
          : j;
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
