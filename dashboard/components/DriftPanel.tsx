"use client";
import type { Drift, DriftPoint } from "@/lib/api";
import Section from "./Section";

const TEXT: Record<string, string> = {
  stable: "text-emerald-500",
  moderate: "text-amber-400",
  significant: "text-red-400",
  insufficient_data: "text-slate-500",
};
const BAR: Record<string, string> = {
  stable: "bg-emerald-500",
  moderate: "bg-amber-400",
  significant: "bg-red-500",
  insufficient_data: "bg-slate-600",
};
const SCALE = 0.5;

function Sparkline({ points }: { points: DriftPoint[] }) {
  if (points.length < 2) return <p className="py-2 text-slate-700">collecting history…</p>;
  const W = 300, H = 36;
  const max = Math.max(0.3, ...points.map((p) => p.psi));
  const x = (i: number) => (i / (points.length - 1)) * W;
  const y = (v: number) => H - (v / max) * H;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-9 w-full" preserveAspectRatio="none">
      <line x1="0" x2={W} y1={y(0.25)} y2={y(0.25)} stroke="#4a4a4a" strokeDasharray="2 3" />
      <polyline
        points={points.map((p, i) => `${x(i)},${y(p.psi)}`).join(" ")}
        fill="none" stroke="#a0a0a0" strokeWidth="1.2" vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export default function DriftPanel({ drift, history }: { drift: Drift | null; history: DriftPoint[] }) {
  const status = drift?.status ?? "insufficient_data";
  const v = drift?.overall_psi ?? null;
  const feats = drift
    ? Object.entries(drift.features)
        .filter(([, d]) => d.psi != null)
        .sort((a, b) => (b[1].psi ?? 0) - (a[1].psi ?? 0))
        .slice(0, 6)
    : [];

  return (
    <Section title="data drift · psi" meta={drift ? `${drift.window_minutes}m window · ${drift.n_samples.toLocaleString()} samples` : ""}>
      <div className="flex items-baseline gap-3">
        <span className="text-3xl tabular-nums text-slate-100">{v == null ? "-" : v.toFixed(2)}</span>
        <span className={TEXT[status]}>{status.replace("_", " ")}</span>
      </div>

      <div className="relative mt-3 h-1.5 bg-slate-900">
        <div className={`h-full ${BAR[status]}`} style={{ width: `${Math.min((v ?? 0) / SCALE, 1) * 100}%` }} />
        <div className="absolute top-0 h-full w-px bg-slate-500" style={{ left: `${(0.1 / SCALE) * 100}%` }} />
        <div className="absolute top-0 h-full w-px bg-slate-500" style={{ left: `${(0.25 / SCALE) * 100}%` }} />
      </div>
      <div className="relative mt-1 h-3 text-[10px] text-slate-600">
        <span className="absolute -translate-x-1/2" style={{ left: `${(0.1 / SCALE) * 100}%` }}>0.10</span>
        <span className="absolute -translate-x-1/2" style={{ left: `${(0.25 / SCALE) * 100}%` }}>0.25</span>
      </div>

      <div className="mt-3"><Sparkline points={history} /></div>

      <ul className="mt-4 space-y-1.5">
        {feats.map(([name, d]) => (
          <li key={name} className="grid grid-cols-[110px_1fr_44px] items-center gap-3">
            <span className="truncate text-slate-400">{name}</span>
            <div className="h-1.5 bg-slate-900">
              <div className={`h-full ${BAR[d.status]}`} style={{ width: `${Math.min((d.psi ?? 0) / SCALE, 1) * 100}%` }} />
            </div>
            <span className="text-right tabular-nums text-slate-500">{d.psi?.toFixed(3)}</span>
          </li>
        ))}
        {feats.length === 0 && <li className="text-slate-600">waiting for enough samples…</li>}
      </ul>
    </Section>
  );
}