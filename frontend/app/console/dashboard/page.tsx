"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  fetchDashboardMetrics,
  ORG_ID,
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

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDashboardMetrics(ORG_ID);
      setMetrics(data);
      setError(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to load dashboard.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const time = metrics ? formatTimeSaved(metrics.time_saved_minutes) : null;

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
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center rounded-xl border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800 disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      <main className="px-6 md:px-10 py-8 max-w-5xl mx-auto">
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
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 md:gap-5">
            {/* Card 1 — Total Tickets Triaged */}
            <div className="rounded-2xl border border-emerald-500/30 bg-slate-950/80 p-5 shadow-[0_18px_50px_rgba(0,0,0,0.85)]">
              <div className="text-3xl md:text-4xl font-black tabular-nums text-emerald-400">
                {metrics.total_triaged}
              </div>
              <div className="mt-1 text-sm font-semibold text-slate-100">
                Total Tickets Triaged
              </div>
              <p className="mt-2 text-[11px] text-slate-500 leading-snug">
                tickets processed by AI
              </p>
            </div>

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

            {/* Card 3 — Human Reviewed */}
            <div className="rounded-2xl border border-blue-500/30 bg-slate-950/80 p-5 shadow-[0_18px_50px_rgba(0,0,0,0.85)]">
              <div className="text-3xl md:text-4xl font-black tabular-nums text-blue-400">
                {metrics.human_reviewed}
              </div>
              <div className="mt-1 text-sm font-semibold text-slate-100">
                Human Reviewed
              </div>
              <p className="mt-2 text-[11px] text-slate-500 leading-snug">
                reviewed by support agents
              </p>
            </div>

            {/* Card 4 — Average Confidence */}
            <div
              className={`rounded-2xl border p-5 shadow-[0_18px_50px_rgba(0,0,0,0.85)] ${confidenceAccentClass(
                metrics.average_confidence,
              )}`}
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
            </div>

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
        )}
      </main>
    </div>
  );
}
