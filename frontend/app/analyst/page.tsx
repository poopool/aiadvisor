"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { toast } from "sonner";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type AnalysisResult = {
  ticker: string;
  timestamp?: string;
  regime?: string;
  no_trade?: boolean;
  reason?: string;
  analysis?: Record<string, unknown>;
  recommendation?: {
    strategy: string;
    contract?: string;
    strike?: number;
    expiry?: string;
    delta?: number;
    credit_est?: number;
    buy_to_close_est?: number;
    safety_check?: string;
    thesis?: string;
  };
  existing_recommendation_id?: string;
};

async function runAnalysis(ticker: string): Promise<AnalysisResult> {
  const res = await fetch(`${API_URL}/analyze/${encodeURIComponent(ticker.trim().toUpperCase())}`, {
    method: "POST",
  });
  const data = await res.json();
  if (!res.ok) throw new Error((data as { detail?: string }).detail || res.statusText);
  return data;
}

export default function AnalystPage() {
  const [ticker, setTicker] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const queryClient = useQueryClient();

  async function handleAnalyze(e: React.FormEvent) {
    e.preventDefault();
    if (!ticker.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const data = await runAnalysis(ticker);
      setResult(data);
      if (data.no_trade || data.recommendation?.strategy === "NONE") {
        toast.info(data.reason || "No trade recommended.");
      } else if (data.existing_recommendation_id) {
        toast.info("Already in queue. Open Queue to approve.");
      } else {
        toast.success("Analysis complete. Recommendation added to queue.");
        queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }

  const isValidRecommendation = result && !result.no_trade && result.recommendation && result.recommendation.strategy !== "NONE";

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-slate-100 mb-2 font-mono">The Analyst</h1>
      <p className="text-slate-400 text-sm mb-6">Manual ticker analysis. Results are added to the Approval Queue when valid.</p>

      <form onSubmit={handleAnalyze} className="flex gap-3 mb-8 max-w-xl">
        <input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          placeholder="Ticker (e.g. NVDA)"
          className="flex-1 rounded-lg bg-slate-800 border border-slate-600 text-slate-100 px-4 py-2 font-mono placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          maxLength={10}
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-lg bg-blue-600 text-white px-5 py-2 font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Analyzing…" : "Analyze"}
        </button>
      </form>

      {result && (
        <div className="rounded-xl bg-slate-800/80 border border-slate-700 p-6 max-w-3xl">
          <h2 className="text-lg font-semibold text-slate-200 mb-4 font-mono">Result: {result.ticker}</h2>
          {result.no_trade && (
            <p className="text-amber-400 text-sm mb-4">{result.reason ?? "No trade."}</p>
          )}
          {result.analysis && (
            <div className="grid grid-cols-2 gap-2 text-sm mb-4">
              {result.analysis.price != null && <span className="text-slate-400">Price <span className="font-mono text-slate-200">{String(result.analysis.price)}</span></span>}
              {result.analysis.rsi_14 != null && <span className="text-slate-400">RSI <span className="font-mono text-slate-200">{String(result.analysis.rsi_14)}</span></span>}
              {result.analysis.trend != null && <span className="text-slate-400">Trend <span className="font-mono text-slate-200">{String(result.analysis.trend)}</span></span>}
              {result.analysis.iv_natr_ratio != null && <span className="text-slate-400">IV/NATR <span className="font-mono text-slate-200">{String(result.analysis.iv_natr_ratio)}</span></span>}
            </div>
          )}
          {result.recommendation && (
            <>
              <div className="border-t border-slate-700 pt-4 mt-4">
                <p className="text-slate-400 text-xs uppercase mb-1">Thesis</p>
                <p className="text-slate-200 text-sm">{result.recommendation.thesis ?? "—"}</p>
              </div>
              {result.recommendation.safety_check && (
                <p className="text-slate-400 text-sm mt-2">Safety: {result.recommendation.safety_check}</p>
              )}
              <div className="flex flex-wrap gap-2 mt-4 font-mono text-sm">
                {result.recommendation.strike != null && <span className="text-slate-300">Strike {result.recommendation.strike}</span>}
                {result.recommendation.credit_est != null && <span className="text-slate-300">Credit {result.recommendation.credit_est}</span>}
                {result.recommendation.delta != null && <span className="text-slate-300">Delta {result.recommendation.delta}</span>}
                {result.recommendation.expiry && <span className="text-slate-300">Expiry {result.recommendation.expiry}</span>}
              </div>
            </>
          )}
          <div className="flex gap-3 mt-6 pt-4 border-t border-slate-700">
            {isValidRecommendation && (
              <Link
                href="/approval-queue"
                className="rounded-lg bg-emerald-600 text-white px-4 py-2 text-sm font-medium hover:bg-emerald-700"
              >
                Open in Queue
              </Link>
            )}
            <button
              type="button"
              onClick={() => { setResult(null); setTicker(""); }}
              className="rounded-lg bg-slate-600 text-slate-200 px-4 py-2 text-sm font-medium hover:bg-slate-500"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
