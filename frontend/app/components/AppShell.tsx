"use client";

import { useQuery } from "@tanstack/react-query";
import { Sidebar } from "./Sidebar";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchHeartbeat(): Promise<{ market_status?: string }> {
  const res = await fetch(`${API_URL}/heartbeat`);
  if (!res.ok) return {};
  return res.json();
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { data: heartbeat } = useQuery({
    queryKey: ["heartbeat"],
    queryFn: fetchHeartbeat,
    refetchInterval: 60000,
  });

  const marketStatus = heartbeat?.market_status;

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100 flex-col">
      {marketStatus === "CLOSED" && (
        <div className="shrink-0 bg-amber-500/20 border-b border-amber-500/40 text-amber-200 px-4 py-2 text-center text-sm">
          Markets are closed. Real-time updates paused.
        </div>
      )}
      {marketStatus === "FORCED" && (
        <div className="shrink-0 bg-purple-500/20 border-b border-purple-500/40 text-purple-200 px-4 py-2 text-center text-sm">
          Dev Mode: Market updates are being forced.
        </div>
      )}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
