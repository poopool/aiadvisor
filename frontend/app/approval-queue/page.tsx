"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

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
    recommendation?: { thesis?: string; safety_check?: string; credit_est?: number };
  } | null;
  created_at: string | null;
  /** A-FIX-05: Present when ?check_stale=1 */
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

export default function ApprovalQueuePage() {
  const queryClient = useQueryClient();
  const { data: recommendations, isLoading, error } = useQuery({
    queryKey: ["recommendations", "PENDING"],
    queryFn: fetchRecommendations,
    refetchInterval: 10000,
  });

  const approveMutation = useMutation({
    mutationFn: approve,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["recommendations"] }),
  });

  const rejectMutation = useMutation({
    mutationFn: reject,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["recommendations"] }),
  });

  if (isLoading) return <div className="p-8">Loading…</div>;
  if (error) return <div className="p-8 text-red-600">Error: {(error as Error).message}</div>;

  return (
    <main className="min-h-screen p-8">
      <h1 className="text-2xl font-bold text-slate-800 mb-6">Approval Queue</h1>
      <p className="text-slate-600 mb-6">PENDING recommendations. Approve to move to Monitor; Reject to dismiss.</p>
      <div className="overflow-x-auto">
        <table className="w-full border border-slate-200 rounded-lg overflow-hidden">
          <thead className="bg-slate-100">
            <tr>
              <th className="text-left p-3">Ticker</th>
              <th className="text-left p-3">Strategy</th>
              <th className="text-left p-3">Strike</th>
              <th className="text-left p-3">Expiry</th>
              <th className="text-left p-3">Thesis / Safety</th>
              <th className="text-left p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {(!recommendations || recommendations.length === 0) && (
              <tr>
                <td colSpan={6} className="p-6 text-slate-500 text-center">
                  No PENDING recommendations.
                </td>
              </tr>
            )}
            {recommendations?.map((r) => (
              <tr key={r.id} className="border-t border-slate-200 hover:bg-slate-50">
                <td className="p-3 font-medium">{r.ticker}</td>
                <td className="p-3">{r.strategy}</td>
                <td className="p-3">{r.strike}</td>
                <td className="p-3">{r.expiry}</td>
                <td className="p-3 max-w-md text-sm text-slate-600">
                  {r.thesis_stale && (
                    <span className="block font-semibold text-amber-600 mb-1">THESIS STALE</span>
                  )}
                  {r.calculated_metrics?.recommendation?.thesis ?? "—"}
                  {r.calculated_metrics?.recommendation?.safety_check && (
                    <span className="block mt-1 text-slate-500">
                      {r.calculated_metrics.recommendation.safety_check}
                    </span>
                  )}
                </td>
                <td className="p-3 flex gap-2">
                  <button
                    onClick={() => approveMutation.mutate(r.id)}
                    disabled={approveMutation.isPending || rejectMutation.isPending}
                    className="rounded bg-green-600 text-white px-3 py-1.5 text-sm hover:bg-green-700 disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => rejectMutation.mutate(r.id)}
                    disabled={approveMutation.isPending || rejectMutation.isPending}
                    className="rounded bg-red-600 text-white px-3 py-1.5 text-sm hover:bg-red-700 disabled:opacity-50"
                  >
                    Reject
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
