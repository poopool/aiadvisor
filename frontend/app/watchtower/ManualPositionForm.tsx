"use client";

import { useState } from "react";
import { toast } from "sonner";

// Keep in sync with backend/app/schemas.py
type ManualPositionPayload = {
  ticker: string;
  strategy: "SHORT_PUT" | "SHORT_CALL";
  short_strike: string;
  expiry_date: string;
  entry_price: string;
  contracts: number;
  sector?: string;
};

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: ManualPositionPayload) => Promise<void>;
};

export function ManualPositionForm({ isOpen, onClose, onSave }: Props) {
  const [payload, setPayload] = useState<ManualPositionPayload>({
    ticker: "",
    strategy: "SHORT_PUT",
    short_strike: "",
    expiry_date: "",
    entry_price: "",
    contracts: 1,
    sector: "",
  });
  const [isSaving, setIsSaving] = useState(false);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setPayload((prev) => ({
      ...prev,
      [name]: name === "contracts" ? parseInt(value, 10) : value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSaving) return;

    // Basic validation
    if (!payload.ticker || !payload.short_strike || !payload.expiry_date || !payload.entry_price) {
        toast.error("Please fill all required fields.");
        return;
    }
    if (new Date(payload.expiry_date) <= new Date()) {
        toast.error("Expiry date must be in the future.");
        return;
    }

    setIsSaving(true);
    try {
      await onSave(payload);
      setPayload({
        ticker: "",
        strategy: "SHORT_PUT",
        short_strike: "",
        expiry_date: "",
        entry_price: "",
        contracts: 1,
        sector: "",
      });
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="relative bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg">
        <div className="p-6">
          <h3 className="text-xl font-bold text-slate-100 mb-2">Add Manual Position</h3>
          <p className="text-sm text-slate-400 mb-6">Enter the details of a position opened externally to start monitoring it.</p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="ticker" className="block text-sm font-medium text-slate-300 mb-1">Ticker</label>
                <input type="text" name="ticker" id="ticker" value={payload.ticker} onChange={handleChange} className="w-full bg-slate-800 border-slate-600 rounded-md px-3 py-2 text-slate-200 focus:ring-indigo-500 focus:border-indigo-500" placeholder="e.g. AAPL" required />
              </div>
              <div>
                <label htmlFor="strategy" className="block text-sm font-medium text-slate-300 mb-1">Strategy</label>
                <select name="strategy" id="strategy" value={payload.strategy} onChange={handleChange} className="w-full bg-slate-800 border-slate-600 rounded-md px-3 py-2 text-slate-200 focus:ring-indigo-500 focus:border-indigo-500">
                  <option value="SHORT_PUT">Short Put</option>
                  <option value="SHORT_CALL">Short Call</option>
                </select>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="short_strike" className="block text-sm font-medium text-slate-300 mb-1">Short Strike</label>
                <input type="number" name="short_strike" id="short_strike" value={payload.short_strike} onChange={handleChange} className="w-full bg-slate-800 border-slate-600 rounded-md px-3 py-2 text-slate-200 focus:ring-indigo-500 focus:border-indigo-500" placeholder="150.00" step="0.01" required />
              </div>
              <div>
                <label htmlFor="expiry_date" className="block text-sm font-medium text-slate-300 mb-1">Expiry Date</label>
                <input type="date" name="expiry_date" id="expiry_date" value={payload.expiry_date} onChange={handleChange} className="w-full bg-slate-800 border-slate-600 rounded-md px-3 py-2 text-slate-200 focus:ring-indigo-500 focus:border-indigo-500" required />
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="entry_price" className="block text-sm font-medium text-slate-300 mb-1">Entry Price (Credit)</label>
                <input type="number" name="entry_price" id="entry_price" value={payload.entry_price} onChange={handleChange} className="w-full bg-slate-800 border-slate-600 rounded-md px-3 py-2 text-slate-200 focus:ring-indigo-500 focus:border-indigo-500" placeholder="4.20" step="0.01" required />
              </div>
              <div>
                <label htmlFor="contracts" className="block text-sm font-medium text-slate-300 mb-1">Contracts</label>
                <input type="number" name="contracts" id="contracts" value={payload.contracts} onChange={handleChange} className="w-full bg-slate-800 border-slate-600 rounded-md px-3 py-2 text-slate-200 focus:ring-indigo-500 focus:border-indigo-500" min="1" step="1" required />
              </div>
            </div>
             <div>
                <label htmlFor="sector" className="block text-sm font-medium text-slate-300 mb-1">Sector (Optional)</label>
                <input type="text" name="sector" id="sector" value={payload.sector} onChange={handleChange} className="w-full bg-slate-800 border-slate-600 rounded-md px-3 py-2 text-slate-200 focus:ring-indigo-500 focus:border-indigo-500" placeholder="e.g. Technology" />
              </div>
            <div className="flex justify-end gap-3 pt-4">
              <button type="button" onClick={onClose} className="px-4 py-2 rounded-md text-slate-300 bg-slate-800 hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-500 focus:ring-offset-slate-900">
                Cancel
              </button>
              <button type="submit" disabled={isSaving} className="px-4 py-2 rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 focus:ring-offset-slate-900 disabled:bg-indigo-500/50 disabled:cursor-not-allowed">
                {isSaving ? "Saving..." : "Save Position"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
