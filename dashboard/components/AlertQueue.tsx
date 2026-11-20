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
  if (alerts.length === 0) {
    return <p className="p-5 text-slate-600">no open alerts. try a card-testing attack.</p>;
  }
  return (
    <ul>
      {alerts.map((a) => {
        const sel = selectedId === a.txn_id;
        return (
          <li key={a.txn_id} className="border-b border-slate-900">
            <button
              onClick={() => onSelect(a.txn_id)}
              className={`block w-full border-l-2 px-4 py-2.5 text-left hover:bg-slate-900 ${
                sel ? "border-slate-300 bg-slate-900" : "border-transparent"
              }`}
            >
              <div className="flex items-baseline justify-between tabular-nums">
                <span className="text-slate-300">{a.card_id.slice(-8)}</span>
                <span className={DECISION_STYLE[a.decision]}>
                  {a.decision} {a.score.toFixed(3)}
                </span>
              </div>
              <p className="mt-1 truncate text-slate-500">
                ${a.amount.toFixed(2)} · {a.reasons[0]?.text ?? "no reason recorded"}
              </p>
            </button>
          </li>
        );
      })}
    </ul>
  );
}