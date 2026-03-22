"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  fetchDashboardMetrics,
  ORG_ID,
  type DashboardDetailKind,
  type DashboardMetrics,
} from "../../../lib/api";

function formatTimeSaved(minutes: number): { value: string; unit: string } {
  if (minutes > 60) {
    const h = minutes / 60;
    const rounded = h >= 10 ? Math.round(h) : Math.round(h * 10) / 10;
    return {
      value: Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1),
      unit: rounded === 1 ? "hour" : "hours",
    };
  }
  return { value: String(minutes), unit: minutes === 1 ? "minute" : "minutes" };
}

function confidenceAccentClass(conf: number): string {
  if (conf > 0.8) return "text-emerald-400 border-emerald-500/40 bg-emerald-500/5";
  if (conf > 0.6) return "text-yellow-300 border-yellow-500/40 bg-yellow-500/5";
  return "text-rose-400 border-rose-500/40 bg-rose-500/5";
}

function confidenceDotClass(conf: number | null | undefined): string {
  if (conf == null || Number.isNaN(Number(conf))) return "bg-slate-600";
  const c = Number(conf);
  if (c > 0.8) return "bg-emerald-500";
  if (c > 0.6) return "bg-yellow-400";
  return "bg-red-500";
}

function Spinner() {
  return (
    <div className="flex justify-center py-10">
      <div
        className="h-9 w-9 border-2 border-slate-700 border-t-emerald-500 rounded-full animate-spin"
        aria-label="Loading"
      />
    </div>
  );
}

type OpenPanel = DashboardDetailKind | null;

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [openPanel, setOpenPanel] = useState<OpenPanel>(null);
  const [panelLoading, setPanelLoading] = useState(false);
  const [panelError, setPanelError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchDashboardMetrics(ORG_ID);
        if (!cancelled) {
          setMetrics(data);
          setError(null);
        }
      } catch (e: unknown) {
        if (!cancelled) {
          const msg =
            e instanceof Error ? e.message : "Failed to load dashboard.";
          setError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDashboardMetrics(
        ORG_ID,
        openPanel ? { detail: openPanel } : undefined,
      );
      setMetrics(data);
      setError(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to load dashboard.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [openPanel]);

  const handleCardToggle = async (kind: DashboardDetailKind) => {
    if (openPanel === kind) {
      setOpenPanel(null);
      setPanelError(null);
      return;
    }
    setOpenPanel(kind);
    setPanelLoading(true);
    setPanelError(null);
    try {
      const data = await fetchDashboardMetrics(ORG_ID, { detail: kind });
      setMetrics(data);
      setPanelError(null);
    } catch (e: unknown) {
      const msg =
        e instanceof Error ? e.message : "Failed to load drill-down data.";
      setPanelError(msg);
    } finally {
      setPanelLoading(false);
    }
  };

  const closePanel = () => {
    setOpenPanel(null);
    setPanelError(null);
  };

  const time = metrics ? formatTimeSaved(metrics.time_saved_minutes) : null;

  const clickableCard =
    "cursor-pointer transition-all hover:brightness-110 focus:outline-none focus:ring-2 focus:ring-emerald-500/50";

  return (
    <div className="min-h-screen bg-gradient-to-b from-black via-slate-950 to-black text-slate-100">
      <header className="w-full border-b border-slate-900 bg-black/70 backdrop-blur flex flex-wrap items-center justify-between gap-3 px-6 md:px-10 py-4">
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href="/console"
            className="text-sm text-emerald-400 hover:text-emerald-300 underline-offset-4 hover:underline"
          >
            ← Back to console
          </Link>
        </div>
        <button
          type="button"
          onClick={() => void refreshDashboard()}
          disabled={loading}
          className="inline-flex items-center rounded-xl border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800 disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      <main className="px-4 sm:px-6 md:px-10 py-8 max-w-5xl mx-auto">
        <h1 className="text-2xl font-bold mb-2">Dashboard</h1>
        <p className="text-sm text-slate-400 mb-8">
          Organization {ORG_ID} — AI triage metrics
        </p>

        {loading && !metrics && (
          <div className="rounded-2xl border border-slate-800 bg-slate-950/80 px-6 py-12 text-center text-slate-400">
            Loading metrics…
          </div>
        )}

        {error && (
          <div className="rounded-2xl border border-rose-800 bg-rose-950/50 px-4 py-3 text-sm text-rose-100 mb-6">
            {error}
          </div>
        )}

        {metrics && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 md:gap-5">
              {/* Card 1 — Total Tickets Triaged (clickable) */}
              <button
                type="button"
                onClick={() => void handleCardToggle("triaged")}
                className={`text-left rounded-2xl border border-emerald-500/30 bg-slate-950/80 p-5 shadow-[0_18px_50px_rgba(0,0,0,0.85)] ${clickableCard} ${
                  openPanel === "triaged" ? "ring-2 ring-emerald-400/60" : ""
                }`}
              >
                <div className="text-3xl md:text-4xl font-black tabular-nums text-emerald-400">
                  {metrics.total_triaged}
                </div>
                <div className="mt-1 text-sm font-semibold text-slate-100">
                  Total Tickets Triaged
                </div>
                <p className="mt-2 text-[11px] text-slate-500 leading-snug">
                  tickets processed by AI
                </p>
              </button>

              {/* Card 2 — Auto Resolved */}
              <div className="rounded-2xl border border-cyan-500/30 bg-slate-950/80 p-5 shadow-[0_18px_50px_rgba(0,0,0,0.85)]">
                <div className="text-3xl md:text-4xl font-black tabular-nums text-cyan-400">
                  {metrics.auto_resolved}
                </div>
                <div className="mt-1 text-sm font-semibold text-slate-100">
                  Auto Resolved
                </div>
                <p className="mt-2 text-[11px] text-slate-500 leading-snug">
                  resolved without human review
                </p>
              </div>

              {/* Card 3 — Human Reviewed (clickable) */}
              <button
                type="button"
                onClick={() => void handleCardToggle("reviewed")}
                className={`text-left rounded-2xl border border-blue-500/30 bg-slate-950/80 p-5 shadow-[0_18px_50px_rgba(0,0,0,0.85)] ${clickableCard} ${
                  openPanel === "reviewed" ? "ring-2 ring-blue-400/60" : ""
                }`}
              >
                <div className="text-3xl md:text-4xl font-black tabular-nums text-blue-400">
                  {metrics.human_reviewed}
                </div>
                <div className="mt-1 text-sm font-semibold text-slate-100">
                  Human Reviewed
                </div>
                <p className="mt-2 text-[11px] text-slate-500 leading-snug">
                  reviewed by support agents
                </p>
              </button>

              {/* Card 4 — Average Confidence (clickable) */}
              <button
                type="button"
                onClick={() => void handleCardToggle("confidence")}
                className={`text-left rounded-2xl border p-5 shadow-[0_18px_50px_rgba(0,0,0,0.85)] ${confidenceAccentClass(
                  metrics.average_confidence,
                )} ${clickableCard} ${
                  openPanel === "confidence" ? "ring-2 ring-white/50" : ""
                }`}
              >
                <div className="text-3xl md:text-4xl font-black tabular-nums">
                  {(metrics.average_confidence * 100).toFixed(0)}%
                </div>
                <div className="mt-1 text-sm font-semibold text-slate-100">
                  Average Confidence
                </div>
                <p className="mt-2 text-[11px] text-slate-500 leading-snug">
                  average AI confidence score
                </p>
              </button>

              {/* Card 5 — Acceptance Rate */}
              <div className="rounded-2xl border border-emerald-500/30 bg-slate-950/80 p-5 shadow-[0_18px_50px_rgba(0,0,0,0.85)]">
                <div className="text-3xl md:text-4xl font-black tabular-nums text-emerald-400">
                  {metrics.acceptance_rate.toFixed(1)}%
                </div>
                <div className="mt-1 text-sm font-semibold text-slate-100">
                  Acceptance Rate
                </div>
                <p className="mt-2 text-[11px] text-slate-500 leading-snug">
                  suggestions accepted by agents
                </p>
              </div>

              {/* Card 6 — Time Saved */}
              <div className="rounded-2xl border border-purple-500/30 bg-slate-950/80 p-5 shadow-[0_18px_50px_rgba(0,0,0,0.85)]">
                <div className="text-3xl md:text-4xl font-black tabular-nums text-purple-400">
                  {time ? `${time.value} ${time.unit}` : "—"}
                </div>
                <div className="mt-1 text-sm font-semibold text-slate-100">
                  Time Saved
                </div>
                <p className="mt-2 text-[11px] text-slate-500 leading-snug">
                  estimated time saved
                </p>
              </div>
            </div>

            {/* Drill-down panel */}
            {openPanel && (
              <section
                className="mt-6 rounded-2xl border border-slate-800 bg-slate-950/90 overflow-hidden shadow-[0_22px_60px_rgba(0,0,0,0.85)]"
                aria-live="polite"
              >
                <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-slate-800 bg-slate-900/80">
                  <h2 className="text-sm font-semibold text-slate-100">
                    {openPanel === "triaged" && "Triaged tickets"}
                    {openPanel === "reviewed" && "Human-reviewed suggestions"}
                    {openPanel === "confidence" && "Confidence breakdown"}
                  </h2>
                  <button
                    type="button"
                    onClick={closePanel}
                    className="rounded-lg px-2 py-1 text-slate-400 hover:text-white hover:bg-slate-800 text-lg leading-none"
                    aria-label="Close panel"
                  >
                    ×
                  </button>
                </div>

                <div className="p-4 md:p-5">
                  {panelLoading && <Spinner />}

                  {panelError && !panelLoading && (
                    <div className="rounded-xl border border-rose-800 bg-rose-950/40 px-4 py-3 text-sm text-rose-100">
                      {panelError}
                    </div>
                  )}

                  {!panelLoading &&
                    !panelError &&
                    openPanel === "triaged" &&
                    metrics.triaged_items && (
                      <div className="overflow-x-auto -mx-4 md:mx-0">
                        <table className="min-w-full text-left text-xs md:text-sm">
                          <thead>
                            <tr className="border-b border-slate-800 text-slate-400">
                              <th className="py-2 pr-3 font-medium">Subject</th>
                              <th className="py-2 pr-3 font-medium">Requester</th>
                              <th className="py-2 pr-3 font-medium whitespace-nowrap">
                                Triage time
                              </th>
                              <th className="py-2 pr-3 font-medium">AI conf.</th>
                              <th className="py-2 pr-3 font-medium">Team</th>
                              <th className="py-2 font-medium">Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {metrics.triaged_items.length === 0 ? (
                              <tr>
                                <td
                                  colSpan={6}
                                  className="py-6 text-slate-500 text-center"
                                >
                                  No triaged tickets yet.
                                </td>
                              </tr>
                            ) : (
                              metrics.triaged_items.map((row) => (
                                <tr
                                  key={`${row.ticket_id}-${row.triage_at}`}
                                  className="border-b border-slate-900/80"
                                >
                                  <td className="py-2 pr-3 text-slate-200 max-w-[180px] truncate">
                                    {row.subject}
                                  </td>
                                  <td className="py-2 pr-3 text-slate-400 whitespace-nowrap">
                                    {row.requester_email}
                                  </td>
                                  <td className="py-2 pr-3 text-slate-400 whitespace-nowrap">
                                    {row.triage_at
                                      ? new Date(
                                          row.triage_at,
                                        ).toLocaleString()
                                      : "—"}
                                  </td>
                                  <td className="py-2 pr-3">
                                    <span className="inline-flex items-center gap-1.5">
                                      <span
                                        className={`inline-block h-2 w-2 rounded-full ${confidenceDotClass(
                                          row.confidence,
                                        )}`}
                                      />
                                      <span className="text-slate-300 tabular-nums">
                                        {row.confidence != null
                                          ? `${(row.confidence * 100).toFixed(0)}%`
                                          : "—"}
                                      </span>
                                    </span>
                                  </td>
                                  <td className="py-2 pr-3 text-slate-400">
                                    {row.suggested_team || "—"}
                                  </td>
                                  <td className="py-2 text-slate-300 capitalize">
                                    {row.ticket_status}
                                  </td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    )}

                  {!panelLoading &&
                    !panelError &&
                    openPanel === "reviewed" &&
                    metrics.reviewed_items && (
                      <div className="overflow-x-auto -mx-4 md:mx-0">
                        <table className="min-w-full text-left text-xs md:text-sm">
                          <thead>
                            <tr className="border-b border-slate-800 text-slate-400">
                              <th className="py-2 pr-3 font-medium">Subject</th>
                              <th className="py-2 pr-3 font-medium">Status</th>
                              <th className="py-2 pr-3 font-medium whitespace-nowrap">
                                Reviewed at
                              </th>
                              <th className="py-2 font-medium">Agent</th>
                            </tr>
                          </thead>
                          <tbody>
                            {metrics.reviewed_items.length === 0 ? (
                              <tr>
                                <td
                                  colSpan={4}
                                  className="py-6 text-slate-500 text-center"
                                >
                                  No reviewed suggestions yet.
                                </td>
                              </tr>
                            ) : (
                              metrics.reviewed_items.map((row, idx) => (
                                <tr
                                  key={`${row.ticket_id}-${row.reviewed_at ?? idx}`}
                                  className="border-b border-slate-900/80"
                                >
                                  <td className="py-2 pr-3 text-slate-200 max-w-[200px]">
                                    {row.subject}
                                  </td>
                                  <td className="py-2 pr-3">
                                    <span
                                      className={
                                        row.suggestion_status === "accepted"
                                          ? "inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/40"
                                          : "inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/40"
                                      }
                                    >
                                      {row.suggestion_status}
                                    </span>
                                  </td>
                                  <td className="py-2 pr-3 text-slate-400 whitespace-nowrap">
                                    {row.reviewed_at
                                      ? new Date(
                                          row.reviewed_at,
                                        ).toLocaleString()
                                      : "—"}
                                  </td>
                                  <td className="py-2 text-slate-300">
                                    {row.reviewer_username ?? "—"}
                                  </td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    )}

                  {!panelLoading &&
                    !panelError &&
                    openPanel === "confidence" &&
                    metrics.confidence_distribution && (
                      <div className="space-y-6">
                        <div className="text-center rounded-xl border border-slate-800 bg-black/40 px-4 py-4">
                          <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">
                            Overall average
                          </div>
                          <div className="text-3xl md:text-4xl font-black tabular-nums text-emerald-400">
                            {(metrics.average_confidence * 100).toFixed(1)}%
                          </div>
                        </div>

                        <div className="space-y-4">
                          {(
                            [
                              {
                                key: "high",
                                label: "High confidence (80–100%)",
                                count: metrics.confidence_distribution.high,
                                pct: metrics.confidence_distribution.high_pct,
                                bar: "bg-emerald-500",
                              },
                              {
                                key: "medium",
                                label: "Medium confidence (60–80%)",
                                count: metrics.confidence_distribution.medium,
                                pct: metrics.confidence_distribution.medium_pct,
                                bar: "bg-yellow-400",
                              },
                              {
                                key: "low",
                                label: "Low confidence (below 60%)",
                                count: metrics.confidence_distribution.low,
                                pct: metrics.confidence_distribution.low_pct,
                                bar: "bg-red-500",
                              },
                            ] as const
                          ).map((band) => (
                            <div key={band.key}>
                              <div className="flex justify-between text-xs mb-1">
                                <span className="text-slate-300">{band.label}</span>
                                <span className="text-slate-400 tabular-nums">
                                  {band.count} ({band.pct.toFixed(1)}%)
                                </span>
                              </div>
                              <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                                <div
                                  className={`h-full rounded-full transition-all ${band.bar}`}
                                  style={{ width: `${Math.min(100, band.pct)}%` }}
                                />
                              </div>
                            </div>
                          ))}
                        </div>

                        {metrics.confidence_distribution.unknown > 0 && (
                          <p className="text-xs text-slate-500">
                            {metrics.confidence_distribution.unknown} suggestion
                            {metrics.confidence_distribution.unknown !== 1
                              ? "s"
                              : ""}{" "}
                            with no confidence score (excluded from bands above).
                          </p>
                        )}
                      </div>
                    )}
                </div>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
