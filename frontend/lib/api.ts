// frontend/lib/api.ts
"use client";

// ---- Shared types ----

export type TicketStatus = "open" | "in_progress" | "resolved";
export type TicketPriority = "low" | "medium" | "high" | "urgent";

export type Ticket = {
  id: number;
  organization: number;
  requester_email: string;
  subject: string;
  body: string;
  status: TicketStatus;
  priority: TicketPriority;
  assigned_team: string;
  created_at: string;
  updated_at: string;
};

export type SuggestionStatus = "pending" | "accepted" | "rejected";

export type Suggestion = {
  id: number;
  organization: number;
  ticket: number;
  job_run: number;
  suggested_priority: TicketPriority | null;
  suggested_team: string;
  draft_reply: string;
  metadata: any;
  status: SuggestionStatus;
  created_at: string;
};

// ---- Base config ----

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

export const ORG_ID: number = Number(
  process.env.NEXT_PUBLIC_ORG_ID ?? "1", // default org id = 1 for local demo
);

// ---- Generic helper ----

export async function apiFetch<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = path.startsWith("http")
    ? path
    : `${API_BASE_URL.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;

  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  // Attach JWT if we have one
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem("nexify_access");
    if (token && !("Authorization" in headers)) {
      (headers as any).Authorization = `Bearer ${token}`;
    }
  }

  const resp = await fetch(url, {
    ...options,
    headers,
  });

  const text = await resp.text();
  let data: any = null;

  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!resp.ok) {
    const msg =
      (data && (data.detail || data.error || data.message)) ||
      `Request failed with status ${resp.status}`;
    throw new Error(msg);
  }

  return data as T;
}

// ---- Auth helpers ----

export async function loginRequest(username: string, password: string) {
  const url = `${API_BASE_URL.replace(/\/$/, "")}/auth/token/`;

  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  const data = await resp.json().catch(() => null);

  if (!resp.ok) {
    const msg =
      (data && (data.detail || data.error || data.message)) ||
      `Login failed with status ${resp.status}`;
    throw new Error(msg);
  }

  return data;
}

export async function fetchMe(accessToken: string) {
  const url = `${API_BASE_URL.replace(/\/$/, "")}/me/`;

  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  const data = await resp.json().catch(() => null);

  if (!resp.ok) {
    const msg =
      (data && (data.detail || data.error || data.message)) ||
      `Failed to load /me (status ${resp.status})`;
    throw new Error(msg);
  }

  return data;
}

// ---- Ticket + suggestion helpers (used by console UI) ----

export async function fetchTicketDetail(
  orgId: number,
  ticketId: number | string,
): Promise<Ticket> {
  return apiFetch<Ticket>(
    `/organizations/${orgId}/tickets/${ticketId}/`,
  );
}

export async function fetchLatestSuggestionForTicket(
  orgId: number,
  ticketId: number | string,
): Promise<Suggestion | null> {
  const data = await apiFetch<{ results?: Suggestion[] }>(
    `/organizations/${orgId}/tickets/${ticketId}/suggestions/?ordering=-created_at&limit=1`,
  );

  const results = data.results ?? [];
  if (results.length === 0) {
    return null;
  }
  return results[0];
}

export async function triggerTriage(
  orgId: number,
  ticketId: number | string,
): Promise<void> {
  // Backend triage endpoint is ticket-based; orgId is just for scoping in callers.
  await apiFetch<void>(
    `/tickets/${ticketId}/trigger-triage/`,
    { method: "POST" },
  );
}

export async function approveSuggestion(
  orgId: number,
  ticketId: number | string,
  suggestionId: number | string,
): Promise<Suggestion> {
  return apiFetch<Suggestion>(
    `/organizations/${orgId}/tickets/${ticketId}/suggestions/${suggestionId}/approve/`,
    { method: "POST" },
  );
}