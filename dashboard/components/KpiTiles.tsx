"use client";
import type { Metrics, Stats } from "@/lib/api";

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export default function KpiTiles({ metrics, stats }: { metrics: Metrics | null; stats: Stats | null }) {
  const l60 = stats?.last_60s;
  const flagged = l60 ? l60.review + l60.decline : 0;
  const rate = l60 && l60.total ? (flagged / l60.total) * 100 : 0;
  const api = metrics?.api_latency_ms;
  const lag = metrics?.stream.lag;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
      <Tile label="Throughput" value={metrics ? `${metrics.throughput_eps.toFixed(0)} eps` : "-"} sub="worker, 5 s avg" />
      <Tile
        label="Scoring latency"
        value={api?.p50 !== undefined ? `${api.p50.toFixed(1)} ms` : "-"}
        sub={api?.p99 !== undefined ? `p99 ${api.p99.toFixed(1)} ms · /score` : "call /score to populate"}
      />
      <Tile label="Stream lag" value={lag == null ? "-" : lag.toLocaleString()} sub={`pending ${metrics?.stream.pending ?? "-"}`} />
      <Tile label="Alert rate (60 s)" value={l60 ? `${rate.toFixed(2)}%` : "-"} sub={l60 ? `${flagged} of ${l60.total}` : undefined} />
      <Tile label="Open alerts" value={stats ? stats.alerts.open.toLocaleString() : "-"} sub={`DLQ ${metrics?.stream.dlq_length ?? "-"}`} />
      <Tile
        label="Analyst precision"
        value={stats?.analyst_precision != null ? `${(stats.analyst_precision * 100).toFixed(0)}%` : "-"}
        sub={stats ? `${stats.alerts.confirmed_fraud} fraud · ${stats.alerts.false_positive} FP` : undefined}
      />
    </div>
  );
}