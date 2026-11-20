"use client";
import type { Decision, Txn } from "@/lib/api";
import Section from "./Section";

export const DECISION_STYLE: Record<Decision, string> = {
  approve: "text-slate-600",
  review: "text-amber-400",
  decline: "text-red-400",
};

export default function LiveFeed({ items }: { items: Txn[] }) {
  return (
    <Section title="live transactions" meta="newest first">
      <div className="max-h-[300px] overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-slate-950 text-slate-600">
            <tr>
              <th className="py-1.5 pr-4 font-normal">time</th>
              <th className="py-1.5 pr-4 font-normal">card</th>
              <th className="py-1.5 pr-6 text-right font-normal">amount</th>
              <th className="py-1.5 pr-6 text-right font-normal">score</th>
              <th className="py-1.5 pr-4 font-normal">decision</th>
              <th className="py-1.5 font-normal">truth</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {items.map((t) => (
              <tr key={t.txn_id} className="border-t border-slate-900">
                <td className="py-1 pr-4 text-slate-500">{new Date(t.scored_at).toLocaleTimeString("en-GB")}</td>
                <td className="py-1 pr-4 text-slate-500">{t.card_id.slice(-8)}</td>
                <td className="py-1 pr-6 text-right text-slate-300">${t.amount.toFixed(2)}</td>
                <td className="py-1 pr-6 text-right text-slate-300">{t.score.toFixed(3)}</td>
                <td className={`py-1 pr-4 ${DECISION_STYLE[t.decision]}`}>{t.decision}</td>
                <td className="py-1 text-red-400/80">{t.true_label === 1 ? `fraud · ${t.pattern}` : ""}</td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="py-8 text-center text-slate-600">
                  no transactions yet. is the simulator running?
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Section>
  );
}