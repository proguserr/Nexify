"use client";

import React, { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { loginRequest, fetchMe, API_BASE_URL } from "../lib/api";

type LoginState = "idle" | "loading" | "success" | "error";

export default function HomePage() {
  const router = useRouter();

  const [username, setUsername] = useState("sb4dec");
  const [password, setPassword] = useState("");
  const [state, setState] = useState<LoginState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [userInfo, setUserInfo] = useState<any | null>(null);

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    setState("loading");
    setError(null);
    setUserInfo(null);

    try {
      // 1) Get JWT tokens
      const tokens = await loginRequest(username, password);
      const access = tokens.access as string;

      // 2) Store access token for /console
      if (typeof window !== "undefined") {
        window.localStorage.setItem("nexify_access", access);
      }

      // 3) Fire off /me for the inspector, but DON'T block redirect on error
      try {
        const meData = await fetchMe(access);
        setUserInfo(meData);
      } catch (innerErr) {
        console.warn("fetchMe failed, but login is fine:", innerErr);
      }

      setState("success");

      // 4) Go to console
      router.push("/console");
    } catch (err: any) {
      console.error("Login error", err);
      setError(err.message || "Failed to login");
      setState("error");
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-black via-slate-950 to-black text-slate-100 flex flex-col">
      {/* Main layout (Nexify top bar comes from layout.tsx) */}
      <main className="flex-1 flex items-center justify-center px-4 py-10 md:px-10">
        <div className="w-full max-w-5xl grid md:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] gap-6 md:gap-10 items-start">
          {/* Login card */}
          <section className="bg-slate-950/80 border border-slate-900 rounded-3xl shadow-[0_24px_80px_rgba(0,0,0,0.9)] p-6 md:p-8">
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

              {/* Status / errors */}
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

          {/* Session inspector / dev panel */}
          <aside className="space-y-4">
            <div className="rounded-3xl border border-slate-900 bg-slate-950/80 p-4 md:p-5 text-xs md:text-sm">
              <h2 className="font-semibold text-slate-100 mb-1">
                Session inspector
              </h2>
              <p className="text-slate-400 text-[11px] md:text-xs mb-3">
                While we&apos;re building Nexify, this panel doubles as a mini
                debugger. After login you&apos;ll see the raw <code>/me</code>{" "}
                payload here.
              </p>

              <div className="mb-1 text-slate-400 text-[11px]">/me response</div>
              <pre className="rounded-xl border border-slate-900 bg-black/80 text-[11px] md:text-xs text-slate-200 p-3 whitespace-pre-wrap break-all max-h-64 overflow-auto">
                {state === "success" && userInfo
                  ? JSON.stringify(userInfo, null, 2)
                  : "// not authenticated yet"}
              </pre>
            </div>

            <div className="rounded-3xl border border-slate-900 bg-slate-950/80 p-4 text-[11px] md:text-xs text-slate-400 space-y-1.5">
              <div>
                <span className="font-semibold text-slate-300">API base URL:</span>{" "}
                {API_BASE_URL}
              </div>
              <div>
                <span className="font-semibold text-slate-300">
                  Next environment:
                </span>{" "}
                {process.env.NODE_ENV}
              </div>
              <div className="text-slate-500">
                Login flow: POST <code>/auth/token/</code> → store{" "}
                <code>access</code> in <code>localStorage</code> → GET{" "}
                <code>/me</code> → go to <code>/console</code>.
              </div>
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}