"use client";

import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen p-8">
      <h1 className="text-2xl font-bold text-slate-800 mb-6">AI Advisor Bot</h1>
      <nav className="flex gap-4">
        <Link
          href="/approval-queue"
          className="rounded bg-slate-700 text-white px-4 py-2 hover:bg-slate-600"
        >
          Approval Queue
        </Link>
        <Link
          href="/watchtower"
          className="rounded bg-slate-700 text-white px-4 py-2 hover:bg-slate-600"
        >
          Watchtower
        </Link>
      </nav>
    </main>
  );
}
