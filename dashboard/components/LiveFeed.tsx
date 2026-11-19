"use client";
import type { Decision, Txn } from "@/lib/api";

export const DECISION_STYLE: Record<Decision, string> = {
  approve: "bg-emerald-500/15 text-emerald-300",
  review: "bg-amber-500/15 text-amber-300",
  decline: "bg-red-500/15 text-red-300",
};

export default function LiveFeed({ items }: { items: Txn[] }) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900">
      <div className="border-b border-slate-800 px-4 py-3">
        <h2 className="text-sm font-semibold">Live transactions</h2>
      </div>
      <div className="max-h-[420px] overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-slate-900 text-slate-500">
            <tr>
              <th className="px-4 py-2">Time</th>
              <th className="px-2 py-2">Card</th>
              <th className="px-2 py-2 text-right">Amount</th>
              <th className="px-2 py-2 text-right">Score</th>
              <th className="px-2 py-2">Decision</th>
              <th className="px-2 py-2">Truth</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.txn_id} className="border-t border-slate-800/60">
                <td className="px-4 py-1.5 tabular-nums text-slate-400">
                  {new Date(t.scored_at).toLocaleTimeString()}
                </td>
                <td className="px-2 py-1.5 font-mono text-slate-400">{t.card_id.slice(-8)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">${t.amount.toFixed(2)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{t.score.toFixed(3)}</td>
                <td className="px-2 py-1.5">
                  <span className={`rounded px-1.5 py-0.5 ${DECISION_STYLE[t.decision]}`}>{t.decision}</span>
                </td>
                <td className="px-2 py-1.5 text-slate-500">
                  {t.true_label === 1 ? `fraud (${t.pattern})` : t.true_label === 0 ? "legit" : "-"}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                  No transactions yet. Is the simulator running?
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}