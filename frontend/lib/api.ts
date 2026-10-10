/**
 * API client helper for CallFlow AI frontend.
 * Communicates with FastAPI backend via Next.js proxy rewrite or direct base URL.
 */

function getBaseUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!envUrl) {
    if (typeof window !== "undefined") return "/api/v1";
    return "http://localhost:8000/api/v1";
  }
  let sanitized = envUrl.trim().replace(/\/+$/, "");
  if (!sanitized.startsWith("http://") && !sanitized.startsWith("https://")) {
    sanitized = `https://${sanitized}`;
  }
  if (!sanitized.endsWith("/api/v1")) {
    sanitized = `${sanitized}/api/v1`;
  }
  return sanitized;
}

const BASE_URL = getBaseUrl();

export async function fetchApi<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("callflow_token") : null;
  const headers = new Headers(options.headers || {});

  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const url = endpoint.startsWith("http") ? endpoint : `${BASE_URL}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  const res = await fetch(url, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || errorBody.message || `Request failed with HTTP ${res.status}`);
  }

  return res.json();
}

// Calls API
export const callsApi = {
  list: (status?: string, limit = 50, offset = 0) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) params.set("status", status);
    return fetchApi(`/calls?${params.toString()}`);
  },
  get: (callId: string) => fetchApi(`/calls/${callId}`),
  whisper: (callId: string, message: string) =>
    fetchApi(`/calls/${callId}/whisper`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  takeover: (callId: string, reason?: string) =>
    fetchApi(`/calls/${callId}/takeover`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
};

// Analytics API
export const analyticsApi = {
  getStats: () => fetchApi("/analytics/dashboard-stats"),
};

// Knowledge API
export const knowledgeApi = {
  listDocuments: () => fetchApi("/knowledge/documents"),
  ingest: (title: string, content: string, sourceType = "faq_manual") =>
    fetchApi("/knowledge/ingest", {
      method: "POST",
      body: JSON.stringify({ title, content, source_type: sourceType }),
    }),
};

// Leads API
export const leadsApi = {
  list: () => fetchApi("/leads"),
  create: (lead: any) =>
    fetchApi("/leads", {
      method: "POST",
      body: JSON.stringify(lead),
    }),
};
