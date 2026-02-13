"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, Fragment } from "react";
import { toast } from "sonner";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Recommendation = {
  id: string;
  ticker: string;
  strategy: string;
  strike: number;
  expiry: string;
  status: string;
  calculated_metrics: {
    analysis?: { price?: number; rsi_14?: number; trend?: string; iv_natr_ratio?: number; expected_move_1sd?: number };
    recommendation?: { thesis?: string; safety_check?: string; credit_est?: number; contract?: string };
  } | null;
  created_at: string | null;
  live_price?: number;
  live_credit?: number;
  thesis_stale?: boolean;
};

async function fetchRecommendations(): Promise<Recommendation[]> {
  const res = await fetch(`${API_URL}/recommendations?status=PENDING&check_stale=true`);
  if (!res.ok) throw new Error("Failed to fetch recommendations");
  return res.json();
}

async function approve(id: string) {
  const res = await fetch(`${API_URL}/recommendations/${id}/approve`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to approve");
  return res.json();
}

async function reject(id: string) {
  const res = await fetch(`${API_URL}/recommendations/${id}/reject`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to reject");
  return res.json();
}

function copyContract(contract: string) {
  navigator.clipboard.writeText(contract);
  toast.success("Contract ID copied");
}

export default function ApprovalQueuePage() {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data: recommendations, isLoading, error } = useQuery({
    queryKey: ["recommendations", "PENDING"],
    queryFn: fetchRecommendations,
    refetchInterval: 10000,
  });

  const approveMutation = useMutation({
    mutationFn: approve,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      toast.success("Recommendation approved");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const rejectMutation = useMutation({
    mutationFn: reject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      toast.success("Recommendation rejected");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  if (isLoading) return <div className="p-8 text-slate-400">Loading…</div>;
  if (error) return <div className="p-8 text-red-400">Error: {(error as Error).message}</div>;

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-slate-100 mb-2 font-mono">Approval Queue</h1>
      <p className="text-slate-400 text-sm mb-6">PENDING recommendations. Approve to move to Monitor; Reject to dismiss.</p>
      <div className="overflow-x-auto rounded-xl border border-slate-700">
        <table className="w-full">
          <thead className="bg-slate-800/80">
            <tr>
              <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Ticker</th>
              <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Strategy</th>
              <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Strike</th>
              <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Expiry</th>
              <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Thesis / Safety</th>
              <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Actions</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {(!recommendations || recommendations.length === 0) && (
              <tr>
                <td colSpan={7} className="p-6 text-slate-500 text-center">
                  No PENDING recommendations.
                </td>
              </tr>
            )}
            {recommendations?.map((r) => {
              const isExpanded = expandedId === r.id;
              const contract = r.calculated_metrics?.recommendation?.contract;
              return (
                <Fragment key={r.id}>
                  <tr
                    className="border-t border-slate-700 hover:bg-slate-800/50 cursor-pointer"
                    onClick={() => setExpandedId(isExpanded ? null : r.id)}
                  >
                    <td className="p-3 font-mono font-medium text-slate-200">{r.ticker}</td>
                    <td className="p-3">
                      <span className="inline-flex items-center rounded-full bg-amber-500/20 text-amber-400 px-2.5 py-0.5 text-xs font-medium">
                        PENDING
                      </span>
                      <span className="ml-2 text-slate-300">{r.strategy}</span>
                    </td>
                    <td className="p-3 font-mono text-slate-200">{r.strike}</td>
                    <td className="p-3 font-mono text-slate-300 text-sm">{r.expiry}</td>
                    <td className="p-3 max-w-md text-sm text-slate-400">
                      {r.thesis_stale && (
                        <span className="block font-semibold text-amber-400 mb-1">THESIS STALE</span>
                      )}
                      {(r.calculated_metrics?.recommendation?.thesis ?? "—").slice(0, 80)}
                      {(r.calculated_metrics?.recommendation?.thesis?.length ?? 0) > 80 ? "…" : ""}
                    </td>
                    <td className="p-3 flex gap-2">
                      <button
                        onClick={(e) => { e.stopPropagation(); approveMutation.mutate(r.id); }}
                        disabled={approveMutation.isPending || rejectMutation.isPending}
                        className="rounded bg-emerald-600 text-white px-3 py-1.5 text-sm hover:bg-emerald-700 disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); rejectMutation.mutate(r.id); }}
                        disabled={approveMutation.isPending || rejectMutation.isPending}
                        className="rounded bg-red-600 text-white px-3 py-1.5 text-sm hover:bg-red-700 disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </td>
                    <td className="p-3">
                      {contract && (
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); copyContract(contract); }}
                          className="text-slate-500 hover:text-slate-300 text-xs"
                          title="Copy contract ID"
                        >
                          Copy
                        </button>
                      )}
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr key={`${r.id}-exp`} className="border-t border-slate-700 bg-slate-800/60">
                      <td colSpan={7} className="p-4 text-sm">
                        <p className="text-slate-400 mb-1 font-medium">Full thesis</p>
                        <p className="text-slate-300 mb-3">{r.calculated_metrics?.recommendation?.thesis ?? "—"}</p>
                        <p className="text-slate-400 mb-1 font-medium">Safety check</p>
                        <p className="text-slate-300">{r.calculated_metrics?.recommendation?.safety_check ?? "—"}</p>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
