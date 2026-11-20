"use client";
import { useState } from "react";
import type { Alert } from "@/lib/api";

export default function ShapInspector({
  alert,
  onFeedback,
}: {
  alert: Alert | null;
  onFeedback: (txnId: string, label: "fraud" | "false_positive") => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);

  if (!alert) {
    return <p className="p-5 text-slate-600">select an alert to see why the model flagged it.</p>;
  }

  const max = Math.max(...alert.shap.map((c) => Math.abs(c.shap)), 0.001);
  const act = async (label: "fraud" | "false_positive") => {
    setBusy(true);
    try {
      await onFeedback(alert.txn_id, label);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm text-slate-100">
            ${alert.amount.toFixed(2)} <span className="text-slate-500">· card {alert.card_id.slice(-8)}</span>
          </p>
          <p className="mt-1 text-slate-500">
            score {alert.score.toFixed(3)} · {alert.decision}
            {alert.true_label === 1 && <span className="text-red-400/80"> · truth: fraud ({alert.pattern})</span>}
          </p>
          <p className="mt-1 text-[11px] text-slate-700">{alert.txn_id}</p>
        </div>
        <div className="flex gap-2">
          <button
            disabled={busy}
            onClick={() => act("fraud")}
            className="border border-red-500/60 px-3 py-1.5 text-red-400 hover:bg-red-500/10 disabled:opacity-40"
          >
            mark fraud
          </button>
          <button
            disabled={busy}
            onClick={() => act("false_positive")}
            className="border border-slate-600 px-3 py-1.5 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
          >
            false positive
          </button>
        </div>
      </div>

      <div className="mt-6 grid gap-8 lg:grid-cols-2">
        <div>
          <h3 className="mb-3 text-[11px] text-slate-500">why it was flagged</h3>
          <ul className="space-y-2.5">
            {alert.reasons.map((r) => (
              <li key={r.feature} className="flex gap-2">
                <span className="text-red-400">›</span>
                <span className="text-slate-300">
                  {r.text} <span className="text-slate-600">{r.shap > 0 ? "+" : ""}{r.shap.toFixed(2)}</span>
                </span>
              </li>
            ))}
            {alert.reasons.length === 0 && <li className="text-slate-600">no reasons recorded.</li>}
          </ul>
        </div>

        <div>
          <h3 className="mb-3 text-[11px] text-slate-500">shap contributions · value</h3>
          <ul className="space-y-1.5">
            {alert.shap.map((c) => {
              const w = (Math.abs(c.shap) / max) * 50;
              const pos = c.shap >= 0;
              return (
                <li key={c.feature} className="grid grid-cols-[120px_1fr_64px] items-center gap-3">
                  <span className="truncate text-slate-400">{c.feature}</span>
                  <div className="relative h-2 bg-slate-900">
                    <div className="absolute left-1/2 top-0 h-full w-px bg-slate-600" />
                    <div
                      className={`absolute top-0 h-full ${pos ? "bg-red-500/80" : "bg-emerald-500/80"}`}
                      style={pos ? { left: "50%", width: `${w}%` } : { right: "50%", width: `${w}%` }}
                    />
                  </div>
                  <span className="text-right tabular-nums text-slate-500">
                    {Number.isInteger(c.value) ? c.value : c.value.toFixed(1)}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-[11px] text-slate-700">red → fraud · green → legitimate</p>
        </div>
      </div>
    </div>
  );
}