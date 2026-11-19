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
    <span className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-emerald-400" : "bg-red-500"}`} />
  );
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-6 py-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">
          SentinelStream <span className="text-slate-500">· Analyst &amp; Drift Console</span>
        </h1>
        {modelVersion && (
          <p className="text-xs text-slate-500">model {modelVersion.slice(0, 19).replace("T", " ")} UTC</p>
        )}
      </div>
      <div className="flex gap-4 text-xs text-slate-400">
        <span className="flex items-center gap-2">{dot(scoringUp)} Scoring API :8010</span>
        <span className="flex items-center gap-2">{dot(simUp)} Simulator :4010</span>
      </div>
    </header>
  );
}