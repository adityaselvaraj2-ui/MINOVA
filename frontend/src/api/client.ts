const API_BASE = "http://127.0.0.1:19823/api/v1";

interface RequestOptions {
  method?: string;
  body?: unknown;
  token?: string;
}

export async function apiFetch<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (opts.token) {
    headers["Authorization"] = `Bearer ${opts.token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method || "GET",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status}: ${detail}`);
  }

  return res.json();
}

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  netguard_active: boolean;
  database: {
    status: string;
    path?: string;
    detail?: string;
  };
  ollama: {
    status: string;
    models?: string[];
    primary_available?: boolean;
    secondary_available?: boolean;
    detail?: string;
  };
}

export function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}
