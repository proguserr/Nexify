"use client";

import React, { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { loginRequest } from "../lib/api";

type LoginState = "idle" | "loading" | "success" | "error";

export default function HomePage() {
  const router = useRouter();

  const [username, setUsername] = useState("sb4dec");
  const [password, setPassword] = useState("");
  const [state, setState] = useState<LoginState>("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    setState("loading");
    setError(null);

    try {
      const tokens = await loginRequest(username, password);
      const access = tokens.access as string;

      if (typeof window !== "undefined") {
        window.localStorage.setItem("nexify_access", access);
      }

      setState("success");
      router.push("/console");
    } catch (err: any) {
      console.error("Login error", err);
      setError(err.message || "Failed to login");
      setState("error");
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-black via-slate-950 to-black text-slate-100 flex flex-col">
      <main className="flex-1 flex items-center justify-center px-4 py-10 md:px-10">
        <section className="w-full max-w-md bg-slate-950/80 border border-slate-900 rounded-3xl shadow-[0_24px_80px_rgba(0,0,0,0.9)] p-6 md:p-8">
          <h1 className="text-2xl md:text-3xl font-semibold mb-2">
            Sign in to <span className="text-emerald-400">Nexify</span>
          </h1>
          <p className="text-sm text-slate-400 mb-6 max-w-md">
            Use your Django user for now (e.g. <code>sb4dec</code>). We&apos;ll
            wire organizations, tickets, and triage flows on top of this
            session.
          </p>

          <form onSubmit={handleLogin} className="space-y-4">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300">
                Username
              </label>
              <input
                className="w-full rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300">
                Password
              </label>
              <input
                type="password"
                className="w-full rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>

            <button
              type="submit"
              disabled={state === "loading"}
              className="mt-2 inline-flex items-center justify-center rounded-xl bg-gradient-to-r from-emerald-400 to-cyan-500 text-slate-950 text-sm font-semibold px-4 py-2.5 shadow-lg shadow-emerald-500/40 disabled:opacity-60 disabled:cursor-not-allowed transition-transform hover:translate-y-[1px]"
            >
              {state === "loading" ? "Logging in..." : "Login"}
            </button>

            <div className="mt-3 text-xs">
              {state === "loading" && (
                <p className="text-amber-300 flex items-center gap-2">
                  <span className="inline-block h-2 w-2 rounded-full bg-amber-300 animate-pulse" />
                  Logging in…
                </p>
              )}
              {state === "success" && (
                <p className="text-emerald-300 flex items-center gap-2">
                  <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
                  Logged in successfully. Redirecting to console…
                </p>
              )}
              {state === "error" && (
                <p className="text-rose-400">
                  <span className="inline-block h-2 w-2 rounded-full bg-rose-500 mr-1" />
                  Login failed
                  {error ? ` – ${error}` : ""}
                </p>
              )}
            </div>
          </form>
        </section>
      </main>
    </div>
  );
}
