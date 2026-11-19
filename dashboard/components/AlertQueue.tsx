"use client";
import type { Alert } from "@/lib/api";
import { DECISION_STYLE } from "./LiveFeed";

export default function AlertQueue({
  alerts,
  selectedId,
  onSelect,
}: {
  alerts: Alert[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900">
      <div className="border-b border-slate-800 px-4 py-3">
        <h2 className="text-sm font-semibold">Open alerts</h2>
      </div>
      <ul className="max-h-[420px] divide-y divide-slate-800/60 overflow-auto">
        {alerts.map((a) => (
          <li key={a.txn_id}>
            <button
              onClick={() => onSelect(a.txn_id)}
              className={`w-full px-4 py-2.5 text-left text-xs hover:bg-slate-800/60 ${
                selectedId === a.txn_id ? "bg-slate-800" : ""
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-slate-400">{a.card_id.slice(-8)}</span>
                <span className={`rounded px-1.5 py-0.5 ${DECISION_STYLE[a.decision]}`}>{a.decision}</span>
              </div>
              <div className="mt-1 flex items-center justify-between tabular-nums">
                <span>${a.amount.toFixed(2)}</span>
                <span className="text-slate-400">score {a.score.toFixed(3)}</span>
              </div>
              <p className="mt-1 truncate text-slate-500">{a.reasons[0]?.text ?? "No reason recorded"}</p>
            </button>
          </li>
        ))}
        {alerts.length === 0 && (
          <li className="px-4 py-8 text-center text-xs text-slate-500">
            No open alerts. Try a card-testing attack.
          </li>
        )}
      </ul>
    </section>
  );
}