"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, Fragment } from "react";
import { toast } from "sonner";
import { ManualPositionForm } from "./ManualPositionForm";

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
        <div className="flex items-center justify-between mb-2">
            <h1 className="text-2xl font-bold text-slate-100 font-mono">Watchtower</h1>
            <button
              onClick={() => setIsFormOpen(true)}
              className="px-4 py-2 rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 focus:ring-offset-slate-900"
            >
              Add Manual Position
            </button>
        </div>
        <p className="text-slate-400 text-sm mb-6">Active positions. Red = stop loss / urgent; Green = near take profit.</p>
        <div className="overflow-x-auto rounded-xl border border-slate-700">
          <table className="w-full">
            <thead className="bg-slate-800/80">
              <tr>
                <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Ticker</th>
                <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Strategy</th>
                <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Strike</th>
                <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Expiry</th>
                <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Entry</th>
                <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Stop / Target</th>
                <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Stage</th>
                <th className="text-left p-3 text-slate-400 text-xs font-medium uppercase">Mark / Freshness</th>
                <th className="w-24" />
              </tr>
            </thead>
            <tbody>
              {(!positions || positions.length === 0) && (
                <tr>
                  <td colSpan={9} className="p-6 text-slate-500 text-center">
                    No active positions.
                  </td>
                </tr>
              )}
              {positions?.map((p) => {
                const isExpanded = expandedId === p.id;
                const isUrgent = p.lifecycle_stage === "CLOSING_URGENT";
                return (
                  <Fragment key={p.id}>
                    <tr
                      className={`border-t border-slate-700 cursor-pointer ${isUrgent ? "bg-red-950/30" : "hover:bg-slate-800/50"}`}
                      onClick={() => setExpandedId(isExpanded ? null : p.id)}
                    >
                      <td className="p-3 font-mono font-medium text-slate-200">{p.ticker}</td>
                      <td className="p-3 text-slate-300">{p.entry_data.strategy}</td>
                      <td className="p-3 font-mono text-slate-200">{p.entry_data.short_strike}</td>
                      <td className="p-3 font-mono text-slate-300 text-sm">{p.entry_data.expiry_date}</td>
                      <td className="p-3 font-mono text-slate-200">{p.entry_data.entry_price} × {p.entry_data.contracts}</td>
                      <td className="p-3">
                        <span className="text-red-400 font-mono">{p.risk_rules.stop_loss_price}</span>
                        <span className="text-slate-500 mx-1">/</span>
                        <span className="text-emerald-400 font-mono">{p.risk_rules.take_profit_price}</span>
                      </td>
                      <td className="p-3">
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            p.lifecycle_stage === "CLOSING_URGENT"
                              ? "bg-red-500/20 text-red-400 animate-pulse"
                              : p.lifecycle_stage === "MONITORING"
                                ? "bg-blue-500/20 text-blue-400"
                                : "bg-slate-500/20 text-slate-400"
                          }`}
                        >
                          {p.lifecycle_stage === "CLOSING_URGENT" ? "CLOSING URGENT" : p.lifecycle_stage}
                        </span>
                      </td>
                      <td className="p-3 text-sm">
                        {p.last_heartbeat?.mark_price != null ? (
                          <span className="font-mono text-slate-200">Mark {p.last_heartbeat.mark_price}</span>
                        ) : (
                          "—"
                        )}
                        {p.last_heartbeat?.data_freshness_status && (
                          <span className="block text-slate-500 text-xs">{p.last_heartbeat.data_freshness_status}</span>
                        )}
                      </td>
                      <td className="p-3 text-right">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            copyContract(p.ticker, p.entry_data.expiry_date, p.entry_data.short_strike, p.entry_data.strategy);
                          }}
                          className="text-slate-500 hover:text-slate-300 text-xs px-2"
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
                          className="text-red-500/80 hover:text-red-400 text-xs px-2 disabled:opacity-50"
                          title="Delete Position"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${p.id}-exp`} className="border-t border-slate-700 bg-slate-800/60">
                        <td colSpan={9} className="p-4 text-sm">
                          <p className="text-slate-400 mb-1 font-medium">Risk rules</p>
                          <p className="text-slate-300 mb-3">
                            Stop: {p.risk_rules.stop_loss_price}, Take profit: {p.risk_rules.take_profit_price}, Max DTE: {p.risk_rules.max_dte_hold}, Force close: {p.risk_rules.force_close_date}
                          </p>
                          <p className="text-slate-400 mb-1 font-medium">Entry data</p>
                          <p className="text-slate-300">
                            {p.entry_data.strategy} @ {p.entry_data.entry_price} × {p.entry_data.contracts}, Expiry {p.entry_data.expiry_date}
                            {p.entry_data.capital_deployed != null && `, Capital deployed: ${p.entry_data.capital_deployed.toFixed(2)}`}
                            {p.entry_data.sector && `, Sector: ${p.entry_data.sector}`}
                          </p>
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
    </>
  );
}
