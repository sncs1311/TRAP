"use client";
import type { Metrics, Stats } from "@/lib/api";

export default function KpiTiles({ metrics, stats }: { metrics: Metrics | null; stats: Stats | null }) {
  const l60 = stats?.last_60s;
  const flagged = l60 ? l60.review + l60.decline : 0;
  const rate = l60 && l60.total ? (flagged / l60.total) * 100 : 0;
  const api = metrics?.api_latency_ms;
  const lag = metrics?.stream.lag;

  const items = [
    { label: "throughput", value: metrics ? `${metrics.throughput_eps.toFixed(0)} eps` : "-", sub: "worker, 5s avg" },
    {
      label: "/score latency p50",
      value: api?.p50 !== undefined ? `${api.p50.toFixed(1)} ms` : "-",
      sub: api?.p99 !== undefined ? `p99 ${api.p99.toFixed(1)} ms` : "run probe to populate",
    },
    { label: "stream lag", value: lag == null ? "-" : lag.toLocaleString(), sub: `pending ${metrics?.stream.pending ?? "-"} · dlq ${metrics?.stream.dlq_length ?? "-"}` },
    { label: "alert rate, 60s", value: l60 ? `${rate.toFixed(2)}%` : "-", sub: l60 ? `${flagged} of ${l60.total}` : "" },
    { label: "open alerts", value: stats ? stats.alerts.open.toLocaleString() : "-", sub: "" },
    {
      label: "analyst precision",
      value: stats?.analyst_precision != null ? `${(stats.analyst_precision * 100).toFixed(0)}%` : "-",
      sub: stats ? `${stats.alerts.confirmed_fraud} fraud · ${stats.alerts.false_positive} fp` : "",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-y-5 border-b border-slate-800 py-5 md:grid-cols-3 lg:grid-cols-6">
      {items.map((it, i) => (
        <div key={it.label} className={i === 0 ? "" : "lg:border-l lg:border-slate-800 lg:pl-5"}>
          <p className="text-[11px] text-slate-500">{it.label}</p>
          <p className="mt-1 text-xl tabular-nums text-slate-100">{it.value}</p>
          <p className="mt-0.5 min-h-[14px] text-[11px] text-slate-600">{it.sub}</p>
        </div>
      ))}
    </div>
  );
}