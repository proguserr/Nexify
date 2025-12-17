"use client";

import React, { useEffect, useState } from "react";
import { apiFetch, API_BASE_URL, ORG_ID } from "../../lib/api";

type Ticket = {
  id: number;
  organization: number;
  requester_email: string;
  subject: string;
  body: string;
  status: "open" | "in_progress" | "resolved";
  priority: "low" | "medium" | "high" | "urgent";
  assigned_team: string;
  created_at: string;
  updated_at: string;
};

type SuggestionStatus = "pending" | "accepted" | "rejected";

type Suggestion = {
  id: number;
  organization: number;
  ticket: number;
  job_run: number;
  suggested_priority: Ticket["priority"] | null;
  suggested_team: string;
  draft_reply: string;
  metadata: any;
  status: SuggestionStatus;
  created_at: string;
};

type TicketEvent = {
  id: number;
  ticket: number;
  event_type: string;
  actor_type: string;
  payload: any;
  created_at: string;
};

type TriageState = "idle" | "loading" | "success" | "error";
type ApproveRejectState = "idle" | "loading" | "success" | "error";

const IDEM_HEADER_NAME = "Idempotency-Key";

export default function ConsolePage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);

  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [draftText, setDraftText] = useState("");
  const [triageState, setTriageState] = useState<TriageState>("idle");
  const [approveState, setApproveState] = useState<ApproveRejectState>("idle");
  const [rejectState, setRejectState] = useState<ApproveRejectState>("idle");

  const [events, setEvents] = useState<TicketEvent[]>([]);

  const [globalError, setGlobalError] = useState<string | null>(null);

  // -------------------------
  // Helpers
  // -------------------------

  function formatDate(iso: string) {
    const d = new Date(iso);
    return d.toLocaleString();
  }

  function priorityLabel(p: Ticket["priority"]) {
    return p.toUpperCase();
  }

  // -------------------------
  // Initial load: tickets
  // -------------------------

  useEffect(() => {
    async function loadTickets() {
      try {
        setGlobalError(null);
        const data = await apiFetch(
          `/organizations/${ORG_ID}/tickets/?ordering=-id`
        );
        const results = data.results ?? [];
        setTickets(results);
        if (results.length > 0) {
          setSelectedTicket(results[0]);
        }
      } catch (err: any) {
        console.error("Failed to load tickets", err);
        setGlobalError(err.message || "Failed to load tickets.");
      }
    }

    loadTickets();
  }, []);

  // -------------------------
  // Whenever selectedTicket changes → load latest suggestion + events
  // -------------------------

  useEffect(() => {
    if (!selectedTicket) return;
    const ticketId = selectedTicket.id;

    async function loadSuggestionAndEvents() {
      try {
        setGlobalError(null);

        // 1) Suggestions (latest first)
        const sugData = await apiFetch(
          `/organizations/${ORG_ID}/tickets/${ticketId}/suggestions/`
        );
        const results: Suggestion[] = sugData.results ?? [];
        const latest = results[0] ?? null;
        setSuggestion(latest);
        setDraftText(latest?.draft_reply ?? "");

        // 2) Events (last few)
        const evData = await apiFetch(
          `/tickets/${ticketId}/events/?ordering=-created_at&limit=10`
        );
        setEvents(evData.results ?? []);
      } catch (err: any) {
        console.error("Failed to load suggestion/events", err);
        setGlobalError(err.message || "Failed to load suggestion/events.");
      }
    }

    loadSuggestionAndEvents();
  }, [selectedTicket]);

  // -------------------------
  // Run AI triage
  // -------------------------

  async function handleRunTriage() {
    if (!selectedTicket) return;

    setTriageState("loading");
    setGlobalError(null);

    const ticketId = selectedTicket.id;
    const idemKey = `console-triage-${ticketId}-${Date.now()}`;

    try {
      // Trigger triage job
      const job = await apiFetch(
        `/tickets/${ticketId}/trigger-triage/`,
        {
          method: "POST",
          headers: {
            [IDEM_HEADER_NAME]: idemKey,
          },
        }
      );

      console.log("Enqueued triage job:", job);

      // Poll suggestions for that ticket a couple of times
      let latest: Suggestion | null = null;

      for (let i = 0; i < 6; i++) {
        await new Promise((r) => setTimeout(r, 1000));

        const sugData = await apiFetch(
          `/organizations/${ORG_ID}/tickets/${ticketId}/suggestions/`
        );
        const results: Suggestion[] = sugData.results ?? [];

        if (results.length > 0) {
          latest = results[0];
          break;
        }
      }

      if (!latest) {
        setTriageState("error");
        setGlobalError(
          "Triage finished but no suggestion was created yet. Try again in a few seconds."
        );
        return;
      }

      setSuggestion(latest);
      setDraftText(latest.draft_reply || "");
      setTriageState("success");
    } catch (err: any) {
      console.error("Triage failed", err);
      setTriageState("error");
      setGlobalError(err.message || "Triage failed.");
    }
  }

  // -------------------------
  // Approve / Reject
  // -------------------------

  async function handleApprove() {
    if (!selectedTicket || !suggestion) return;

    setApproveState("loading");
    setGlobalError(null);

    try {
      const res = await apiFetch(
        `/organizations/${ORG_ID}/tickets/${selectedTicket.id}/suggestions/${suggestion.id}/approve/`,
        {
          method: "POST",
        }
      );

      // Update local suggestion status
      const newStatus: SuggestionStatus = res.status ?? "accepted";
      const updated: Suggestion = {
        ...suggestion,
        status: newStatus,
        draft_reply: draftText,
      };
      setSuggestion(updated);
      setApproveState("success");
    } catch (err: any) {
      console.error("Approve failed", err);
      setApproveState("error");
      setGlobalError(err.message || "Approve failed.");
    }
  }

  async function handleReject() {
    if (!selectedTicket || !suggestion) return;

    setRejectState("loading");
    setGlobalError(null);

    try {
      const res = await apiFetch(
        `/organizations/${ORG_ID}/tickets/${selectedTicket.id}/suggestions/${suggestion.id}/reject/`,
        {
          method: "POST",
        }
      );

      const newStatus: SuggestionStatus = res.status ?? "rejected";
      const updated: Suggestion = {
        ...suggestion,
        status: newStatus,
      };
      setSuggestion(updated);
      setRejectState("success");
    } catch (err: any) {
      console.error("Reject failed", err);
      setRejectState("error");
      setGlobalError(err.message || "Reject failed.");
    }
  }

  // -------------------------
  // Render
  // -------------------------

  return (
    <div className="min-h-screen bg-gradient-to-b from-black via-slate-950 to-black text-slate-100">
      {/* Top bar */}
      <header className="w-full border-b border-slate-900 bg-black/70 backdrop-blur flex items-center justify-between px-6 md:px-10 py-4">
        <div className="flex items-center gap-3">
          <div className="inline-flex h-9 w-9 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 via-teal-400 to-cyan-500 shadow-lg shadow-emerald-500/40">
            <span className="text-lg font-black text-slate-950">N</span>
          </div>
          <div className="flex flex-col leading-none">
            <span className="text-2xl font-black tracking-tight">
              <span className="text-slate-50">N</span>
              <span className="text-emerald-400">exify</span>
            </span>
            <span className="text-[11px] md:text-xs uppercase tracking-[0.18em] text-slate-400/80">
              AI-native ticket triage console
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className="px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/40">
            Backend: online
          </span>
          <span className="px-3 py-1 rounded-full bg-slate-800/80 text-slate-300 border border-slate-700">
            Environment: local dev
          </span>
        </div>
      </header>

      {/* Global error banner */}
      {globalError && (
        <div className="mx-6 md:mx-10 mt-4 rounded-xl bg-rose-900/80 border border-rose-700 px-4 py-2 text-sm text-rose-100">
          {globalError}
        </div>
      )}

      <main className="px-6 md:px-10 py-8">
        <div className="grid lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1.2fr)] gap-6 lg:gap-8 items-start">
          {/* Ticket list */}
          <section className="bg-slate-950/80 border border-slate-900 rounded-3xl p-5 md:p-6 shadow-[0_22px_60px_rgba(0,0,0,0.9)]">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold">Ticket list</h2>
                <p className="text-xs text-slate-400">
                  First page of tickets for organization {ORG_ID}.
                </p>
              </div>
              <span className="text-[11px] px-2 py-1 rounded-full bg-slate-900 text-slate-400 border border-slate-800">
                {tickets.length} tickets loaded
              </span>
            </div>

            <div className="space-y-1.5">
              {tickets.map((t) => {
                const isSelected = selectedTicket?.id === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => setSelectedTicket(t)}
                    className={`w-full text-left rounded-2xl border px-3 py-2.5 mb-1 transition-colors ${
                      isSelected
                        ? "border-emerald-500/70 bg-emerald-500/8"
                        : "border-slate-800 bg-slate-950/60 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-medium">{t.subject}</div>
                        <div className="text-[11px] text-slate-400">
                          {t.requester_email}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <span className="inline-flex items-center rounded-full border border-slate-700 px-2 py-[2px] text-[10px] uppercase tracking-wide text-slate-300">
                          {priorityLabel(t.priority)}
                        </span>
                        <span className="inline-flex items-center rounded-full border border-emerald-600/50 px-2 py-[2px] text-[10px] uppercase tracking-wide text-emerald-300">
                          {t.status === "resolved" ? "Resolved" : "Open"}
                        </span>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="mt-4 text-[11px] text-slate-500">
              API base URL: <span className="text-slate-300">{API_BASE_URL}</span>
            </div>
          </section>

          {/* Ticket detail + triage */}
          <section className="bg-slate-950/80 border border-slate-900 rounded-3xl p-5 md:p-6 shadow-[0_22px_60px_rgba(0,0,0,0.9)]">
            {selectedTicket ? (
              <>
                <header className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="text-lg font-semibold">
                      {selectedTicket.subject}
                    </h2>
                    <div className="flex flex-wrap gap-2 mt-1 text-[11px] text-slate-400">
                      <span>{selectedTicket.requester_email}</span>
                      <span>•</span>
                      <span>{formatDate(selectedTicket.created_at)}</span>
                      <span>•</span>
                      <span className="inline-flex items-center rounded-full border border-emerald-600/50 px-2 py-[1px] text-[10px] uppercase tracking-wide text-emerald-300">
                        {selectedTicket.status === "resolved"
                          ? "Resolved"
                          : "Open"}
                      </span>
                      <span className="inline-flex items-center rounded-full border border-amber-500/60 px-2 py-[1px] text-[10px] uppercase tracking-wide text-amber-300">
                        {priorityLabel(selectedTicket.priority)}
                      </span>
                    </div>
                  </div>
                </header>

                {/* Body */}
                <div className="mb-4">
                  <div className="text-[11px] text-slate-400 mb-1">
                    Ticket body
                  </div>
                  <div className="rounded-2xl border border-slate-800 bg-black/60 px-3 py-2.5 text-sm text-slate-100">
                    {selectedTicket.body}
                  </div>
                </div>

                {/* Triage controls */}
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <button
                    onClick={handleRunTriage}
                    disabled={triageState === "loading"}
                    className="inline-flex items-center justify-center rounded-xl bg-emerald-500 text-slate-950 text-xs font-semibold px-3 py-1.5 disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {triageState === "loading" ? "Running triage…" : "Run AI triage"}
                  </button>
                  {suggestion && (
                    <span className="px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/40 text-[11px]">
                      Suggestion {suggestion.status === "pending"
                        ? "ready"
                        : suggestion.status}
                    </span>
                  )}
                </div>

                {/* Suggestion panel */}
                <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4 mb-4">
                  <div className="text-[11px] font-semibold text-slate-400 mb-2">
                    AI triage suggestion
                  </div>

                  {suggestion ? (
                    <>
                      <label className="block text-[11px] text-slate-400 mb-1">
                        Draft resolution text
                      </label>
                      <textarea
                        className="w-full min-h-[140px] rounded-xl border border-slate-700 bg-black/70 px-3 py-2 text-xs text-slate-100 outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 mb-3"
                        value={draftText}
                        onChange={(e) => setDraftText(e.target.value)}
                      />

                      <div className="flex flex-wrap items-center gap-2 mb-3 text-[11px] text-slate-400">
                        <span>
                          Status:{" "}
                          <span className="text-slate-100">
                            {suggestion.status}
                          </span>
                        </span>
                        <span>•</span>
                        <span>
                          Team:{" "}
                          <span className="text-slate-100">
                            {suggestion.suggested_team || "support"}
                          </span>
                        </span>
                        <span>•</span>
                        <span>
                          Priority:{" "}
                          <span className="text-slate-100">
                            {suggestion.suggested_priority?.toUpperCase() ||
                              "MEDIUM"}
                          </span>
                        </span>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={handleApprove}
                          disabled={approveState === "loading"}
                          className="inline-flex items-center justify-center rounded-xl bg-emerald-500 text-slate-950 text-xs font-semibold px-3 py-1.5 disabled:opacity-60 disabled:cursor-not-allowed"
                        >
                          {approveState === "loading"
                            ? "Approving…"
                            : "Approve & apply"}
                        </button>
                        <button
                          onClick={handleReject}
                          disabled={rejectState === "loading"}
                          className="inline-flex items-center justify-center rounded-xl bg-slate-800 text-slate-100 text-xs font-semibold px-3 py-1.5 border border-slate-700 disabled:opacity-60 disabled:cursor-not-allowed"
                        >
                          {rejectState === "loading" ? "Rejecting…" : "Reject"}
                        </button>
                      </div>
                    </>
                  ) : (
                    <div className="text-xs text-slate-500">
                      No suggestion yet. Run AI triage to generate one.
                    </div>
                  )}
                </div>

                {/* Events */}
                <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
                  <div className="text-[11px] font-semibold text-slate-400 mb-2">
                    Recent events
                  </div>
                  {events.length === 0 ? (
                    <div className="text-xs text-slate-500">
                      No events recorded yet.
                    </div>
                  ) : (
                    <ul className="space-y-1.5 text-[11px] text-slate-300">
                      {events.map((ev) => (
                        <li
                          key={ev.id}
                          className="flex justify-between gap-3 border-b border-slate-800/70 pb-1 last:border-b-0"
                        >
                          <span>
                            <span className="font-mono uppercase text-slate-400">
                              {ev.event_type}
                            </span>
                            {ev.payload?.suggestion_id && (
                              <span className="text-slate-500">
                                {" "}
                                · suggestion {ev.payload.suggestion_id}
                              </span>
                            )}
                          </span>
                          <span className="text-slate-500">
                            {formatDate(ev.created_at)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            ) : (
              <div className="text-sm text-slate-500">
                No tickets loaded. Seed some demo tickets and refresh.
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}