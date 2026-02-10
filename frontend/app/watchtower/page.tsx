"use client";

import { useQuery } from "@tanstack/react-query";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Position = {
  id: string;
  ticker: string;
  status: string;
  lifecycle_stage: string;
  entry_data: {
    strategy: string;
    short_strike: number;
    expiry_date: string;
    entry_price: number;
    contracts: number;
  };
  risk_rules: {
    stop_loss_price: number;
    take_profit_price: number;
    max_dte_hold: number;
    force_close_date: string;
  };
  last_heartbeat: { mark_price?: number; data_freshness_status?: string } | null;
  created_at: string | null;
};

async function fetchPositions(): Promise<Position[]> {
  const res = await fetch(`${API_URL}/positions`);
  if (!res.ok) throw new Error("Failed to fetch positions");
  return res.json();
}

export default function WatchtowerPage() {
  const { data: positions, isLoading, error } = useQuery({
    queryKey: ["positions"],
    queryFn: fetchPositions,
    refetchInterval: 30000,
  });

  if (isLoading) return <div className="p-8">Loading…</div>;
  if (error) return <div className="p-8 text-red-600">Error: {(error as Error).message}</div>;

  return (
    <main className="min-h-screen p-8">
      <h1 className="text-2xl font-bold text-slate-800 mb-6">Watchtower</h1>
      <p className="text-slate-600 mb-6">Active positions. Red = stop loss / urgent; Green = near take profit.</p>
      <div className="overflow-x-auto">
        <table className="w-full border border-slate-200 rounded-lg overflow-hidden">
          <thead className="bg-slate-100">
            <tr>
              <th className="text-left p-3">Ticker</th>
              <th className="text-left p-3">Strategy</th>
              <th className="text-left p-3">Strike</th>
              <th className="text-left p-3">Expiry</th>
              <th className="text-left p-3">Entry</th>
              <th className="text-left p-3">Stop / Target</th>
              <th className="text-left p-3">Stage</th>
              <th className="text-left p-3">Mark / Freshness</th>
            </tr>
          </thead>
          <tbody>
            {(!positions || positions.length === 0) && (
              <tr>
                <td colSpan={8} className="p-6 text-slate-500 text-center">
                  No active positions.
                </td>
              </tr>
            )}
            {positions?.map((p) => (
              <tr
                key={p.id}
                className={`border-t border-slate-200 ${
                  p.lifecycle_stage === "CLOSING_URGENT" ? "bg-red-50" : "hover:bg-slate-50"
                }`}
              >
                <td className="p-3 font-medium">{p.ticker}</td>
                <td className="p-3">{p.entry_data.strategy}</td>
                <td className="p-3">{p.entry_data.short_strike}</td>
                <td className="p-3">{p.entry_data.expiry_date}</td>
                <td className="p-3">{p.entry_data.entry_price} × {p.entry_data.contracts}</td>
                <td className="p-3">
                  <span className="text-red-600">{p.risk_rules.stop_loss_price}</span>
                  {" / "}
                  <span className="text-green-600">{p.risk_rules.take_profit_price}</span>
                </td>
                <td className="p-3">
                  <span
                    className={
                      p.lifecycle_stage === "CLOSING_URGENT"
                        ? "text-red-600 font-medium"
                        : p.lifecycle_stage === "MONITORING"
                          ? "text-slate-700"
                          : "text-slate-500"
                    }
                  >
                    {p.lifecycle_stage}
                  </span>
                </td>
                <td className="p-3 text-sm">
                  {p.last_heartbeat?.mark_price != null ? `Mark ${p.last_heartbeat.mark_price}` : "—"}
                  {p.last_heartbeat?.data_freshness_status && (
                    <span className="block text-slate-500">{p.last_heartbeat.data_freshness_status}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
