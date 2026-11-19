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
    return (
      <section className="rounded-lg border border-slate-800 bg-slate-900 p-6 text-sm text-slate-500">
        Select an alert to see why the model flagged it.
      </section>
    );
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
    <section className="rounded-lg border border-slate-800 bg-slate-900">
      <div className="flex items-start justify-between gap-4 border-b border-slate-800 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">Reason-code inspector</h2>
          <p className="mt-1 font-mono text-xs text-slate-500">{alert.txn_id}</p>
          <p className="mt-1 text-xs text-slate-400">
            ${alert.amount.toFixed(2)} · score {alert.score.toFixed(3)} · {alert.decision}
            {alert.true_label === 1 && ` · truth: fraud (${alert.pattern})`}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            disabled={busy}
            onClick={() => act("fraud")}
            className="rounded bg-red-600 px-3 py-1.5 text-xs font-medium hover:bg-red-500 disabled:opacity-50"
          >
            Mark Fraud
          </button>
          <button
            disabled={busy}
            onClick={() => act("false_positive")}
            className="rounded bg-slate-700 px-3 py-1.5 text-xs font-medium hover:bg-slate-600 disabled:opacity-50"
          >
            False Positive
          </button>
        </div>
      </div>

      <div className="grid gap-6 p-4 md:grid-cols-2">
        <div>
          <h3 className="mb-2 text-xs uppercase tracking-wide text-slate-500">Why it was flagged</h3>
          <ul className="space-y-2 text-sm">
            {alert.reasons.map((r) => (
              <li key={r.feature} className="flex gap-2">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-red-400" />
                <span>
                  {r.text} <span className="text-xs text-slate-500">({r.shap > 0 ? "+" : ""}{r.shap.toFixed(2)})</span>
                </span>
              </li>
            ))}
            {alert.reasons.length === 0 && <li className="text-slate-500">No reasons recorded.</li>}
          </ul>
        </div>

        <div>
          <h3 className="mb-2 text-xs uppercase tracking-wide text-slate-500">
            SHAP contributions (log-odds)
          </h3>
          <ul className="space-y-1.5 text-xs">
            {alert.shap.map((c) => {
              const w = (Math.abs(c.shap) / max) * 50;
              const pos = c.shap >= 0;
              return (
                <li key={c.feature} className="grid grid-cols-[110px_1fr_70px] items-center gap-2">
                  <span className="truncate text-slate-400">{c.feature}</span>
                  <div className="relative h-3 rounded bg-slate-800">
                    <div className="absolute left-1/2 top-0 h-full w-px bg-slate-600" />
                    <div
                      className={`absolute top-0 h-full rounded ${pos ? "bg-red-500" : "bg-emerald-500"}`}
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
          <p className="mt-2 text-xs text-slate-600">Red pushes toward fraud, green toward legitimate.</p>
        </div>
      </div>
    </section>
  );
}