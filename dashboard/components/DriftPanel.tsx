"use client";
import type { Drift, DriftPoint } from "@/lib/api";

const COLOR: Record<string, string> = {
  stable: "#34d399",
  moderate: "#fbbf24",
  significant: "#f87171",
  insufficient_data: "#64748b",
};

function Gauge({ value, status, max = 1.0 }: { value: number | null; status: string; max?: number }) {
  const R = 70, CX = 90, CY = 90;
  const frac = value == null ? 0 : Math.min(value / max, 1);
  const pt = (f: number) => {
    const a = Math.PI * (1 - f);
    return [CX + R * Math.cos(a), CY - R * Math.sin(a)];
  };
  const arc = (f0: number, f1: number) => {
    const [x0, y0] = pt(f0), [x1, y1] = pt(f1);
    return `M ${x0} ${y0} A ${R} ${R} 0 0 1 ${x1} ${y1}`;
  };
  return (
    <svg viewBox="0 0 180 110" className="mx-auto w-full max-w-[260px]">
      <path d={arc(0, 1)} stroke="#1e293b" strokeWidth="14" fill="none" strokeLinecap="round" />
      <path d={arc(0, 0.1 / max)} stroke="#34d399" strokeWidth="14" fill="none" opacity="0.25" />
      <path d={arc(0.1 / max, 0.25 / max)} stroke="#fbbf24" strokeWidth="14" fill="none" opacity="0.25" />
      <path d={arc(0.25 / max, 1)} stroke="#f87171" strokeWidth="14" fill="none" opacity="0.25" />
      {frac > 0.001 && (
        <path d={arc(0, frac)} stroke={COLOR[status]} strokeWidth="14" fill="none" strokeLinecap="round" />
      )}
      <text x={CX} y={CY - 8} textAnchor="middle" fill="#e2e8f0" fontSize="26" fontWeight="600">
        {value == null ? "-" : value.toFixed(2)}
      </text>
      <text x={CX} y={CY + 10} textAnchor="middle" fill={COLOR[status]} fontSize="10">
        {status.replace("_", " ")}
      </text>
    </svg>
  );
}

function Sparkline({ points }: { points: DriftPoint[] }) {
  if (points.length < 2) {
    return <p className="py-3 text-center text-xs text-slate-600">Collecting history...</p>;
  }
  const W = 300, H = 50;
  const ys = points.map((p) => p.psi);
  const max = Math.max(0.3, ...ys);
  const x = (i: number) => (i / (points.length - 1)) * W;
  const y = (v: number) => H - (v / max) * H;
  const line = points.map((p, i) => `${x(i)},${y(p.psi)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="none">
      <line x1="0" x2={W} y1={y(0.25)} y2={y(0.25)} stroke="#f87171" strokeDasharray="3 3" opacity="0.5" />
      <line x1="0" x2={W} y1={y(0.1)} y2={y(0.1)} stroke="#fbbf24" strokeDasharray="3 3" opacity="0.5" />
      <polyline points={line} fill="none" stroke="#60a5fa" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export default function DriftPanel({ drift, history }: { drift: Drift | null; history: DriftPoint[] }) {
  const feats = drift
    ? Object.entries(drift.features)
        .filter(([, d]) => d.psi != null)
        .sort((a, b) => (b[1].psi ?? 0) - (a[1].psi ?? 0))
    : [];
  const top = Math.max(0.3, ...feats.map(([, d]) => d.psi ?? 0));
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900">
      <div className="border-b border-slate-800 px-4 py-3">
        <h2 className="text-sm font-semibold">Data drift (PSI)</h2>
        <p className="text-xs text-slate-500">
          Last {drift?.window_minutes ?? "-"} min vs training · {drift?.n_samples.toLocaleString() ?? "-"} samples
        </p>
      </div>
      <div className="p-4">
        <Gauge value={drift?.overall_psi ?? null} status={drift?.status ?? "insufficient_data"} />
        <div className="mt-1">
          <Sparkline points={history} />
          <p className="text-center text-[10px] text-slate-600">overall PSI, last 30 min (dashed: 0.10 / 0.25)</p>
        </div>
        <ul className="mt-4 space-y-1.5 text-xs">
          {feats.map(([name, d]) => (
            <li key={name} className="grid grid-cols-[110px_1fr_48px] items-center gap-2">
              <span className="truncate text-slate-400">{name}</span>
              <div className="h-2 rounded bg-slate-800">
                <div
                  className="h-2 rounded"
                  style={{ width: `${Math.min(((d.psi ?? 0) / top) * 100, 100)}%`, background: COLOR[d.status] }}
                />
              </div>
              <span className="text-right tabular-nums text-slate-400">{d.psi?.toFixed(3)}</span>
            </li>
          ))}
          {feats.length === 0 && <li className="text-slate-600">Waiting for enough samples...</li>}
        </ul>
      </div>
    </section>
  );
}