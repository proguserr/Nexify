// frontend/app/console/tickets/[ticketId]/page.tsx
"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  API_BASE_URL,
  Ticket,
  Suggestion,
  fetchTicketDetail,
  fetchLatestSuggestionForTicket,
  triggerTriage,
  approveSuggestion,
} from "../../../../lib/api";

type LoadState = "idle" | "loading" | "success" | "error";

const ORG_ID = 1; // for now

export default function TicketDetailPage({
  params,
}: {
  params: { ticketId: string };
}) {
  const ticketId = Number(params.ticketId);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);

  const [ticketState, setTicketState] = useState<LoadState>("idle");
  const [suggestionState, setSuggestionState] = useState<LoadState>("idle");
  const [triageRunning, setTriageRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticketId) return;
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketId]);

  async function loadAll() {
    setTicketState("loading");
    setSuggestionState("loading");
    setError(null);

    try {
      const [t, s] = await Promise.all([
        fetchTicketDetail(ORG_ID, ticketId),
        fetchLatestSuggestionForTicket(ORG_ID, ticketId),
      ]);

      setTicket(t);
      setTicketState("success");

      setSuggestion(s);
      setSuggestionState("success");
    } catch (err: any) {
      console.error(err);
      setError(err.message ?? "Failed to load ticket");
      setTicketState("error");
      setSuggestionState("error");
    }
  }

  async function handleRunTriage() {
    if (!ticketId) return;
    setTriageRunning(true);
    setError(null);

    try {
      await triggerTriage(ORG_ID, ticketId);
      const s = await fetchLatestSuggestionForTicket(ORG_ID, ticketId);
      setSuggestion(s);
      setSuggestionState("success");
    } catch (err: any) {
      console.error(err);
      setError(err.message ?? "Failed to run triage");
    } finally {
      setTriageRunning(false);
    }
  }

  async function handleApprove() {
    if (!suggestion) return;
    setSuggestionState("loading");
    setError(null);

    try {
      const updated = await approveSuggestion(suggestion.id);
      setSuggestion(updated);
      setSuggestionState("success");
    } catch (err: any) {
      console.error(err);
      setError(err.message ?? "Failed to apply suggestion");
      setSuggestionState("error");
    }
  }

  function formatDate(iso?: string) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  return (
    <div className="min-h-[calc(100vh-56px)] bg-gradient-to-br from-black via-slate-950 to-black text-slate-100 px-4 py-8 md:px-10">
      <div className="mx-auto max-w-6xl space-y-6">
        {/* Breadcrumb + actions */}
        <div className="flex items-center justify-between gap-3">
          <div className="space-y-1">
            <Link
              href="/console"
              className="text-xs text-slate-400 hover:text-emerald-300"
            >
              ← Back to tickets
            </Link>
            <h1 className="text-2xl md:text-3xl font-semibold">
              Ticket #{ticketId}
            </h1>
            {ticket && (
              <p className="text-sm text-slate-400">
                {ticket.subject || "Untitled ticket"}
              </p>
            )}
          </div>

          <div className="flex flex-col items-end gap-2">
            <div className="flex gap-2">
              <button
                onClick={loadAll}
                className="px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-900/80 text-xs text-slate-200 hover:border-slate-500"
              >
                Refresh
              </button>
              <button
                onClick={handleRunTriage}
                disabled={triageRunning}
                className="px-3 py-1.5 rounded-xl bg-gradient-to-r from-emerald-400 to-cyan-500 text-xs font-semibold text-slate-950 shadow-md shadow-emerald-500/40 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {triageRunning ? "Running AI triage…" : "Run AI triage"}
              </button>
            </div>
            {error && (
              <p className="text-[11px] text-rose-300 max-w-xs text-right">
                {error}
              </p>
            )}
          </div>
        </div>

        {/* Two-column layout */}
        <div className="grid md:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] gap-6 md:gap-8 items-start">
          {/* Ticket details */}
          <section className="rounded-3xl border border-slate-900 bg-slate-950/70 p-5 md:p-6 space-y-4">
            <h2 className="text-sm font-semibold text-slate-200 mb-1">
              Ticket details
            </h2>

            {ticketState === "loading" && (
              <p className="text-sm text-slate-400">Loading ticket…</p>
            )}

            {ticketState === "error" && (
              <p className="text-sm text-rose-300">
                Failed to load ticket. {error}
              </p>
            )}

            {ticket && (
              <>
                <div className="space-y-1">
                  <div className="text-xs text-slate-400">Subject</div>
                  <div className="text-sm text-slate-100">
                    {ticket.subject || "Untitled ticket"}
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="text-xs text-slate-400">Body</div>
                  <div className="text-sm text-slate-200 whitespace-pre-wrap">
                    {ticket.body || "—"}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="space-y-1">
                    <div className="text-slate-400">Priority</div>
                    <span className="inline-flex items-center rounded-full border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-[11px] capitalize">
                      {ticket.priority}
                    </span>
                  </div>
                  <div className="space-y-1">
                    <div className="text-slate-400">Status</div>
                    <div className="capitalize">{ticket.status}</div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-slate-400">Team</div>
                    <div>{ticket.assigned_team || "—"}</div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-slate-400">Created</div>
                    <div>{formatDate(ticket.created_at)}</div>
                  </div>
                </div>
              </>
            )}
          </section>

          {/* Triage suggestion panel */}
          <section className="rounded-3xl border border-slate-900 bg-slate-950/70 p-5 md:p-6 space-y-4">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-slate-200">
                  AI triage suggestion
                </h2>
                <p className="text-[11px] text-slate-400 mt-1">
                  Run Nexify on this ticket. Approving will push the suggested
                  priority / team back to Django.
                </p>
              </div>
              {suggestion && (
                <span className="px-3 py-1 rounded-full bg-slate-900 text-[11px] border border-slate-700 text-slate-300 capitalize">
                  Status: {suggestion.status || "pending"}
                </span>
              )}
            </div>

            {suggestionState === "loading" && (
              <p className="text-sm text-slate-400">Loading suggestion…</p>
            )}

            {suggestionState === "error" && (
              <p className="text-sm text-rose-300">
                Failed to load suggestion. {error}
              </p>
            )}

            {!suggestion && suggestionState === "success" && (
              <p className="text-sm text-slate-400">
                No triage suggestion yet. Click{" "}
                <span className="font-medium">Run AI triage</span> to create
                one.
              </p>
            )}

            {suggestion && (
              <>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="space-y-1">
                    <div className="text-slate-400">Suggested priority</div>
                    <span className="inline-flex items-center rounded-full border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-[11px] capitalize">
                      {suggestion.suggested_priority}
                    </span>
                  </div>
                  <div className="space-y-1">
                    <div className="text-slate-400">Suggested team</div>
                    <div>{suggestion.suggested_team || "—"}</div>
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="text-xs text-slate-400">Draft reply</div>
                  <div className="text-sm text-slate-200 whitespace-pre-wrap rounded-2xl bg-slate-950/80 border border-slate-800 px-3 py-2">
                    {suggestion.draft_reply || "—"}
                  </div>
                </div>

                <div className="flex items-center justify-between gap-3 pt-2">
                  <button
                    onClick={handleApprove}
                    disabled={suggestionState === "loading"}
                    className="inline-flex items-center justify-center rounded-xl bg-emerald-500 text-slate-950 text-xs font-semibold px-3 py-1.5 shadow-md shadow-emerald-500/40 disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {suggestionState === "loading"
                      ? "Applying…"
                      : "Approve & apply"}
                  </button>

                  <div className="text-[11px] text-slate-500 text-right">
                    API base URL: <span className="font-mono">{API_BASE_URL}</span>
                  </div>
                </div>
              </>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}