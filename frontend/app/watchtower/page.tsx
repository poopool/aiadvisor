"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { ManualPositionForm } from "./ManualPositionForm";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Greeks = { delta?: number; theta?: number; gamma?: number };

/** Matches backend Position schema (GET /positions). A-FIX-17: includes market_value, unrealized_pnl, return_pct, greeks. */
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
    capital_deployed?: number;
    sector?: string;
  };
  risk_rules: {
    stop_loss_price: number;
    take_profit_price: number;
    max_dte_hold: number;
    force_close_date: string;
  };
  last_heartbeat: { mark_price?: number; data_freshness_status?: string } | null;
  created_at: string | null;
  market_value?: number | string | null;
  unrealized_pnl?: number | string | null;
  return_pct?: number | string | null;
  greeks?: Greeks | null;
};

type ManualPositionPayload = {
  ticker: string;
  strategy: "SHORT_PUT" | "SHORT_CALL";
  short_strike: string;
  expiry_date: string;
  entry_price: string;
  contracts: number;
  sector?: string;
};

async function fetchPositions(): Promise<Position[]> {
  const res = await fetch(`${API_URL}/positions`);
  if (!res.ok) throw new Error("Failed to fetch positions");
  return res.json();
}

async function createManualPosition(payload: ManualPositionPayload) {
  const res = await fetch(`${API_URL}/positions/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorData = await res.json();
    throw new Error(errorData.detail || "Failed to create position");
  }
  return res.json();
}

async function deletePosition(positionId: string) {
  const res = await fetch(`${API_URL}/positions/${positionId}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) {
    const errorData = await res.json();
    throw new Error(errorData.detail || "Failed to delete position");
  }
}

function copyContract(ticker: string, expiry: string, strike: number, strategy: string) {
  const type = strategy.includes("PUT") ? "P" : "C";
  const contract = `${ticker}${expiry.replace(/-/g, "").slice(2)}${type}${Math.round(strike * 1000).toString().padStart(8, "0")}`;
  navigator.clipboard.writeText(contract);
  toast.success("Contract ID copied");
}

function num(x: number | string | null | undefined): number | null {
  if (x == null) return null;
  if (typeof x === "string") {
    const n = parseFloat(x);
    return Number.isFinite(n) ? n : null;
  }
  return Number.isFinite(x) ? x : null;
}

function formatStrategy(strategy: string, strike: number): string {
  const type = strategy.includes("PUT") ? "Put" : "Call";
  return `$${strike} ${type}`;
}

export default function WatchtowerPage() {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data: positions, isLoading, error } = useQuery({
    queryKey: ["positions"],
    queryFn: fetchPositions,
    refetchInterval: 30000,
  });

  const createMutation = useMutation({
    mutationFn: createManualPosition,
    onSuccess: () => {
      toast.success("Manual position added successfully.");
      queryClient.invalidateQueries({ queryKey: ["positions"] });
      setIsFormOpen(false);
    },
    onError: (err: Error) => {
      toast.error(`Failed to add position: ${err.message}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deletePosition,
    onSuccess: () => {
      toast.success("Position deleted successfully.");
      queryClient.invalidateQueries({ queryKey: ["positions"] });
    },
    onError: (err: Error) => {
      toast.error(`Failed to delete position: ${err.message}`);
    },
  });

  const handleSavePosition = async (payload: ManualPositionPayload) => {
    await createMutation.mutateAsync(payload);
  };

  const handleDeletePosition = (positionId: string, ticker: string) => {
    if (window.confirm(`Are you sure you want to delete the ${ticker} position? This cannot be undone.`)) {
      deleteMutation.mutate(positionId);
    }
  };

  const totalMarketValue = positions?.reduce((sum, p) => sum + (num(p.market_value) ?? 0), 0) ?? 0;
  const totalUnrealizedPnl = positions?.reduce((sum, p) => sum + (num(p.unrealized_pnl) ?? 0), 0) ?? 0;

  if (isLoading) return <div className="p-8 text-slate-400">Loading…</div>;
  if (error) return <div className="p-8 text-red-400">Error: {(error as Error).message}</div>;

  return (
    <>
      <ManualPositionForm
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        onSave={handleSavePosition}
      />
      <div className="p-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-slate-100 font-mono">Watchtower</h1>
          <button
            onClick={() => setIsFormOpen(true)}
            className="px-4 py-2 rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 focus:ring-offset-slate-900"
          >
            Add Manual Position
          </button>
        </div>

        {/* A-P11-04: Portfolio Summary Header */}
        <section className="mb-8 p-6 rounded-xl bg-slate-800/60 border border-slate-700">
          <h2 className="text-slate-400 text-sm font-medium uppercase tracking-wider mb-4">Portfolio Value</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <div>
              <p className="text-slate-500 text-xs uppercase mb-1">Total Market Value</p>
              <p className="text-2xl sm:text-3xl font-mono font-bold text-slate-100">
                ${totalMarketValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
            </div>
            <div>
              <p className="text-slate-500 text-xs uppercase mb-1">Total Daily P&L</p>
              <p className="text-2xl sm:text-3xl font-mono font-bold text-slate-400">—</p>
              <p className="text-slate-500 text-xs mt-0.5">(Prior day mark not stored)</p>
            </div>
            <div>
              <p className="text-slate-500 text-xs uppercase mb-1">Total Unrealized P&L</p>
              <p
                className={`text-2xl sm:text-3xl font-mono font-bold ${
                  totalUnrealizedPnl >= 0 ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {totalUnrealizedPnl >= 0 ? "+" : ""}
                ${totalUnrealizedPnl.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
            </div>
          </div>
          {/* Optional placeholder for equity curve sparkline */}
          <div className="mt-4 h-10 rounded bg-slate-700/50 flex items-center justify-center">
            <span className="text-slate-500 text-xs">Equity curve sparkline (placeholder)</span>
          </div>
        </section>

        <p className="text-slate-400 text-sm mb-4">Active positions. Click a card to expand details.</p>

        {/* A-P11-03: List of Cards layout (replacing table) */}
        <div className="flex flex-col gap-2">
          {(!positions || positions.length === 0) && (
            <div className="p-8 rounded-xl border border-slate-700 text-center text-slate-500">
              No active positions.
            </div>
          )}
          {positions?.map((p) => {
            const isExpanded = expandedId === p.id;
            const isUrgent = p.lifecycle_stage === "CLOSING_URGENT";
            const mv = num(p.market_value);
            const retPct = num(p.return_pct);
            const strategyLabel = formatStrategy(p.entry_data.strategy, p.entry_data.short_strike);
            const diversityPct =
              totalMarketValue > 0 && mv != null ? (mv / totalMarketValue) * 100 : null;

            return (
              <div
                key={p.id}
                className={`rounded-xl border cursor-pointer transition-colors ${
                  isUrgent ? "border-red-500/50 bg-red-950/20" : "border-slate-700 bg-slate-800/50 hover:bg-slate-800/70"
                }`}
                onClick={() => setExpandedId(isExpanded ? null : p.id)}
              >
                {/* Card row: Left = Ticker + Strategy, Right = Market Value + Total Return % */}
                <div className="p-4 flex flex-wrap items-center justify-between gap-4">
                  <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3">
                    <span className="font-bold text-slate-100 text-lg">{p.ticker}</span>
                    <span className="text-slate-400 text-sm">{strategyLabel}</span>
                    {isUrgent && (
                      <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium bg-red-500/20 text-red-400 animate-pulse">
                        CLOSING URGENT
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <p className="text-slate-500 text-xs uppercase">Market Value</p>
                      <p className="font-mono text-lg font-semibold text-slate-200">
                        {mv != null ? `$${mv.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-slate-500 text-xs uppercase">Total Return</p>
                      <p
                        className={`font-mono text-lg font-semibold ${
                          retPct != null ? (retPct >= 0 ? "text-emerald-400" : "text-red-400") : "text-slate-400"
                        }`}
                      >
                        {retPct != null ? `${retPct >= 0 ? "+" : ""}${retPct.toFixed(2)}%` : "—"}
                      </p>
                    </div>
                    <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          copyContract(p.ticker, p.entry_data.expiry_date, p.entry_data.short_strike, p.entry_data.strategy);
                        }}
                        className="px-2 py-1 text-slate-500 hover:text-slate-300 text-xs rounded"
                        title="Copy contract ID"
                      >
                        Copy
                      </button>
                      <button
                        type="button"
                        disabled={deleteMutation.isPending}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeletePosition(p.id, p.ticker);
                        }}
                        className="px-2 py-1 text-red-500/80 hover:text-red-400 text-xs rounded disabled:opacity-50"
                        title="Delete Position"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>

                {/* A-P11-05: Position Detail Expansion — Robinhood-style stats grid */}
                {isExpanded && (
                  <div className="border-t border-slate-700 bg-slate-900/50 p-4 text-sm">
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
                      <div>
                        <p className="text-slate-500 text-xs uppercase mb-0.5">Avg Cost</p>
                        <p className="font-mono text-slate-200">{p.entry_data.entry_price}</p>
                      </div>
                      <div>
                        <p className="text-slate-500 text-xs uppercase mb-0.5">Mark Price</p>
                        <p className="font-mono text-slate-200">
                          {p.last_heartbeat?.mark_price != null ? p.last_heartbeat.mark_price : "—"}
                        </p>
                      </div>
                      <div>
                        <p className="text-slate-500 text-xs uppercase mb-0.5">Today&apos;s Return</p>
                        <p className="font-mono text-slate-400">—</p>
                      </div>
                      <div>
                        <p className="text-slate-500 text-xs uppercase mb-0.5">Total Return</p>
                        <p
                          className={`font-mono ${retPct != null ? (retPct >= 0 ? "text-emerald-400" : "text-red-400") : "text-slate-400"}`}
                        >
                          {retPct != null ? `${retPct >= 0 ? "+" : ""}${retPct.toFixed(2)}%` : "—"}
                        </p>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                      <div>
                        <p className="text-slate-500 text-xs uppercase mb-0.5">Portfolio Diversity</p>
                        <p className="font-mono text-slate-200">
                          {diversityPct != null ? `${diversityPct.toFixed(1)}%` : "—"}
                        </p>
                      </div>
                      {p.greeks && (
                        <>
                          <div>
                            <p className="text-slate-500 text-xs uppercase mb-0.5">Delta</p>
                            <p className="font-mono text-slate-200">{p.greeks.delta ?? "—"}</p>
                          </div>
                          <div>
                            <p className="text-slate-500 text-xs uppercase mb-0.5">Theta</p>
                            <p className="font-mono text-slate-200">{p.greeks.theta ?? "—"}</p>
                          </div>
                          <div>
                            <p className="text-slate-500 text-xs uppercase mb-0.5">Gamma</p>
                            <p className="font-mono text-slate-200">{p.greeks.gamma ?? "—"}</p>
                          </div>
                        </>
                      )}
                    </div>
                    <div className="mt-4 pt-3 border-t border-slate-700">
                      <p className="text-slate-500 text-xs uppercase mb-1">Risk rules</p>
                      <p className="text-slate-300">
                        Stop: <span className="font-mono">{p.risk_rules.stop_loss_price}</span>, Take profit:{" "}
                        <span className="font-mono">{p.risk_rules.take_profit_price}</span>, Max DTE:{" "}
                        {p.risk_rules.max_dte_hold}, Force close: {p.risk_rules.force_close_date}
                      </p>
                      <p className="text-slate-500 text-xs mt-1">
                        {p.entry_data.strategy} @ {p.entry_data.entry_price} × {p.entry_data.contracts}, Expiry{" "}
                        {p.entry_data.expiry_date}
                        {p.entry_data.capital_deployed != null &&
                          ` · Capital deployed: $${p.entry_data.capital_deployed.toFixed(2)}`}
                        {p.entry_data.sector && ` · ${p.entry_data.sector}`}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
