"use client";

export default function Header({
  scoringUp,
  simUp,
  modelVersion,
}: {
  scoringUp: boolean;
  simUp: boolean;
  modelVersion?: string;
}) {
  const dot = (ok: boolean) => (
    <span className={ok ? "text-emerald-500" : "text-red-500"}>●</span>
  );
  return (
    <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-slate-800 py-4">
      <div className="flex items-baseline gap-4">
        <h1 className="text-sm text-slate-100">
          TRAP <span className="ml-1 text-slate-600">transaction risk &amp; anomaly pipeline</span>
        </h1>
        {modelVersion && (
          <span className="text-slate-600">model {modelVersion.slice(0, 16).replace("T", " ")} utc</span>
        )}
      </div>
      <div className="flex gap-5 text-slate-500">
        <span>{dot(scoringUp)} scoring :8010</span>
        <span>{dot(simUp)} simulator :4010</span>
      </div>
    </header>
  );
}