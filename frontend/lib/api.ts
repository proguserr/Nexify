// frontend/lib/api.ts
"use client";

// NOTE: minimal placeholders so TS knows these exist.
// Replace `any` with real fields when your API shape is final.
export type Ticket = any;
export type Suggestion = any;

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

export const ORG_ID: number = Number(
  process.env.NEXT_PUBLIC_ORG_ID ?? "1" // default org id = 1 for local demo
);

// Generic helper that automatically:
// - prefixes with API_BASE_URL
// - attaches Authorization: Bearer <access token> from localStorage (nexify_access)
// - parses JSON and throws on non-2xx
export async function apiFetch<T = any>(
  path: string,
  options: RequestInit = {}
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

// --- Auth helpers used on the login page ---

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

// --- Ticket detail & suggestion helpers for Nexify console ---

export async function fetchTicketDetail(ticketId: string): Promise<Ticket> {
  const res = await fetch(
    `${API_BASE_URL.replace(/\/$/, "")}/tickets/${ticketId}`,
  );

  if (!res.ok) {
    throw new Error(`Failed to fetch ticket ${ticketId}`);
  }

  return (await res.json()) as Ticket;
}

export async function fetchLatestSuggestionForTicket(
  ticketId: string,
): Promise<Suggestion | null> {
  const res = await fetch(
    `${API_BASE_URL.replace(/\/$/, "")}/tickets/${ticketId}/suggestions/latest`,
  );

  if (res.status === 404) {
    // No suggestion yet
    return null;
  }

  if (!res.ok) {
    throw new Error(
      `Failed to fetch latest suggestion for ticket ${ticketId}`,
    );
  }

  return (await res.json()) as Suggestion;
}

export async function triggerTriage(ticketId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL.replace(/\/$/, "")}/tickets/${ticketId}/triage`,
    {
      method: "POST",
    },
  );

  if (!res.ok) {
    throw new Error(`Failed to trigger triage for ticket ${ticketId}`);
  }
}

export async function approveSuggestion(ticketId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL.replace(/\/$/, "")}/tickets/${ticketId}/approve`,
    {
      method: "POST",
    },
  );

  if (!res.ok) {
    throw new Error(`Failed to approve suggestion for ticket ${ticketId}`);
  }
}