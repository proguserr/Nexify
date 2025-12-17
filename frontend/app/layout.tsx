// frontend/app/layout.tsx
import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nexify",
  description: "AI-native ticket triage console",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#020617] text-slate-100 antialiased">
        <div className="min-h-screen flex flex-col">
          {/* Global top bar */}
          <header className="border-b border-slate-900/80 bg-black/60 backdrop-blur">
            <div className="mx-auto max-w-6xl px-4 md:px-8 py-3 flex items-center justify-between">
              <Link href="/" className="flex items-center gap-3">
                {/* Logo */}
                <div className="inline-flex h-8 w-8 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 via-teal-400 to-cyan-500 shadow-lg shadow-emerald-500/40">
                  <span className="text-sm font-black text-slate-950">N</span>
                </div>
                <div className="flex flex-col leading-none">
                  <span className="text-lg font-semibold tracking-tight">
                    <span className="text-emerald-400">Nexify</span>
                  </span>
                  <span className="text-[11px] uppercase tracking-[0.16em] text-slate-400/80">
                    AI-native ticket triage console
                  </span>
                </div>
              </Link>

              <div className="flex items-center gap-2 text-[11px]">
                <span className="px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/40">
                  Backend: <span className="font-semibold">online</span>
                </span>
                <span className="px-3 py-1 rounded-full bg-slate-950 text-slate-300 border border-slate-700">
                  Environment: <span className="font-semibold">local dev</span>
                </span>
              </div>
            </div>
          </header>

          {/* Page content */}
          <main className="flex-1">{children}</main>
        </div>
      </body>
    </html>
  );
}