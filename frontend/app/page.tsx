"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchHeartbeat(): Promise<{ type?: string; timestamp?: string; message?: string }> {
  const res = await fetch(`${API_URL}/heartbeat`);
  if (!res.ok) throw new Error("Heartbeat failed");
  return res.json();
}

async function fetchPositionsCount(): Promise<number> {
  const res = await fetch(`${API_URL}/positions`);
  if (!res.ok) return 0;
  const data = await res.json();
  return Array.isArray(data) ? data.length : 0;
}

async function fetchPendingCount(): Promise<number> {
  const res = await fetch(`${API_URL}/recommendations?status=PENDING`);
  if (!res.ok) return 0;
  const data = await res.json();
  return Array.isArray(data) ? data.length : 0;
}

async function runBatch(): Promise<unknown> {
  const res = await fetch(`${API_URL}/analyze/batch`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || res.statusText);
  }
  return res.json();
}

export default function DashboardPage() {
  const queryClient = useQueryClient();

  const { data: heartbeat, isLoading: heartbeatLoading, error: heartbeatError } = useQuery({
    queryKey: ["heartbeat"],
    queryFn: fetchHeartbeat,
    refetchInterval: 60000,
  });

  const { data: positionsCount = 0 } = useQuery({
    queryKey: ["positions", "count"],
    queryFn: fetchPositionsCount,
    refetchInterval: 30000,
  });

  const { data: pendingCount = 0 } = useQuery({
    queryKey: ["recommendations", "PENDING", "count"],
    queryFn: fetchPendingCount,
    refetchInterval: 15000,
  });

  const batchMutation = useMutation({
    mutationFn: runBatch,
    onSuccess: (data) => {
      const payload = data as { blocked?: boolean; reason?: string; results?: unknown[] } | unknown[];
      if (payload && typeof payload === "object" && "blocked" in payload && payload.blocked) {
        toast.info(payload.reason || "Batch blocked.");
        return;
      }
      const results = Array.isArray(payload) ? payload : (payload as { results?: unknown[] })?.results ?? [];
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      toast.success(`Batch complete. ${results.length} recommendation(s) added to queue.`);
    },
    onError: (err: Error) => {
      toast.error(err.message || "Batch analysis failed");
    },
  });

  const isHealthy = !heartbeatError && heartbeat != null;

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-slate-100 mb-6 font-mono">Command Center</h1>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 mb-8">
        {/* A-UI-03: System Health — Green pulse when OK */}
        <div className="rounded-xl bg-slate-800/80 border border-slate-700 p-5">
          <h2 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-3">System Health</h2>
          <div className="flex items-center gap-3">
            <span
              className={`inline-block h-3 w-3 rounded-full ${
                heartbeatLoading ? "animate-pulse bg-slate-500" : isHealthy ? "bg-emerald-500 animate-pulse" : "bg-red-500"
              }`}
              title={isHealthy ? "Online" : "Error"}
            />
            <span className="text-slate-200 font-mono text-sm">
              {heartbeatLoading ? "Checking…" : isHealthy ? "Online" : "Unavailable"}
            </span>
          </div>
          {heartbeat?.timestamp && (
            <p className="text-xs text-slate-500 mt-2 font-mono">{heartbeat.timestamp}</p>
          )}
        </div>

        {/* Quick Stats */}
        <div className="rounded-xl bg-slate-800/80 border border-slate-700 p-5">
          <h2 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-3">Active Positions</h2>
          <p className="text-2xl font-mono font-semibold text-slate-100">{positionsCount}</p>
        </div>
        <div className="rounded-xl bg-slate-800/80 border border-slate-700 p-5">
          <h2 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-3">Pending Approvals</h2>
          <p className="text-2xl font-mono font-semibold text-slate-100">{pendingCount}</p>
        </div>
      </div>

      {/* Batch Trigger */}
      <div className="rounded-xl bg-slate-800/80 border border-slate-700 p-5 max-w-md">
        <h2 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-3">Batch Analysis</h2>
        <p className="text-sm text-slate-300 mb-4">Run analysis on liquid universe (S&P 500 filter).</p>
        <button
          onClick={() => batchMutation.mutate()}
          disabled={batchMutation.isPending}
          className="rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {batchMutation.isPending ? "Running…" : "Trigger batch"}
        </button>
      </div>
    </div>
  );
}
