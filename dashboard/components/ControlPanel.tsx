"use client";
import { useState } from "react";
import { SCORING, SIM, postJson, type SimStatus } from "@/lib/api";

function Btn({
  children,
  onClick,
  tone = "default",
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  tone?: "default" | "danger" | "warn" | "ok";
  disabled?: boolean;
}) {
  const tones = {
    default: "bg-slate-700 hover:bg-slate-600",
    danger: "bg-red-600 hover:bg-red-500",
    warn: "bg-amber-600 hover:bg-amber-500",
    ok: "bg-emerald-600 hover:bg-emerald-500",
  };
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className={`rounded px-3 py-1.5 text-xs font-medium disabled:opacity-40 ${tones[tone]}`}
    >
      {children}
    </button>
  );
}

export default function ControlPanel({ sim, onChanged }: { sim: SimStatus | null; onChanged: () => void }) {
  const [msg, setMsg] = useState<string>("");
  const [rps, setRps] = useState(20);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    try {
      await fn();
      setMsg(`${label}: ok`);
    } catch (e) {
      setMsg(`${label} failed: ${e instanceof Error ? e.message : e}`);
    }
    onChanged();
  };

  const d = sim?.drift;
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900">
      <div className="border-b border-slate-800 px-4 py-3">
        <h2 className="text-sm font-semibold">Chaos controls</h2>
        <p className="text-xs text-slate-500">
          {sim
            ? `${sim.mode} · ${sim.running ? "running" : "paused"} · ${sim.actual_eps.toFixed(0)} eps actual · backlog ${sim.backlog}`
            : "simulator unreachable"}
        </p>
      </div>
      <div className="space-y-4 p-4">
        <div>
          <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Traffic</p>
          <div className="flex flex-wrap items-center gap-2">
            <Btn
              tone="warn"
              disabled={sim?.burst.active}
              onClick={() => run("burst", () => postJson(`${SIM}/control/burst`, { rps: 300, duration_s: 20 }))}
            >
              {sim?.burst.active ? `Burst ${sim.burst.seconds_left.toFixed(0)} s left` : "Simulate Traffic Burst (300 rps, 20 s)"}
            </Btn>
            <Btn onClick={() => run(sim?.running ? "pause" : "resume", () => postJson(`${SIM}/control/${sim?.running ? "stop" : "start"}`))}>
              {sim?.running ? "Pause" : "Resume"}
            </Btn>
          </div>
          <div className="mt-3 flex items-center gap-2 text-xs text-slate-400">
            <label htmlFor="rps">Base rate</label>
            <input
              id="rps"
              type="number"
              min={0}
              max={2000}
              value={rps}
              onChange={(e) => setRps(Number(e.target.value))}
              className="w-20 rounded border border-slate-700 bg-slate-950 px-2 py-1"
            />
            <span>rps</span>
            <Btn onClick={() => run("rps", () => postJson(`${SIM}/control/rps`, { rps }))}>Set</Btn>
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Attacks</p>
          <div className="flex flex-wrap gap-2">
            <Btn tone="danger" onClick={() => run("card-testing", () => postJson(`${SIM}/control/attack`, { kind: "card_testing", n_attacks: 3 }))}>
              Card-testing attack ×3
            </Btn>
            <Btn tone="danger" onClick={() => run("takeover", () => postJson(`${SIM}/control/attack`, { kind: "takeover", n_attacks: 3 }))}>
              Account takeover ×3
            </Btn>
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">
            Distribution drift
            {d?.active && (
              <span className="ml-2 normal-case text-amber-400">
                active · ramp {(d.progress * 100).toFixed(0)}%
              </span>
            )}
          </p>
          <div className="flex flex-wrap gap-2">
            <Btn tone="warn" onClick={() => run("mild drift", () => postJson(`${SIM}/control/drift`, { preset: "mild", ramp_seconds: 30 }))}>
              Inject mild drift
            </Btn>
            <Btn tone="danger" onClick={() => run("severe drift", () => postJson(`${SIM}/control/drift`, { preset: "severe", ramp_seconds: 30 }))}>
              Inject severe drift
            </Btn>
            <Btn tone="ok" onClick={() => run("clear drift", () => postJson(`${SIM}/control/drift/clear`, {}))}>
              Clear drift
            </Btn>
          </div>
        </div>

        <div className="border-t border-slate-800 pt-3">
          <Btn
            onClick={() =>
              run("probe /score", async () => {
                // generates a few direct /score calls so the API latency tile has fresh data
                for (let i = 0; i < 20; i++) {
                  await postJson(`${SCORING}/score`, {
                    card_id: `probe-${Date.now()}-${i}`,
                    amount: 20 + i,
                    merchant_cat: 0,
                    is_online: 0,
                    distance_km: 3,
                    is_foreign: 0,
                    account_age_days: 900,
                  });
                }
              })
            }
          >
            Probe /score latency (20 calls)
          </Btn>
        </div>

        {msg && <p className="text-xs text-slate-500">{msg}</p>}
      </div>
    </section>
  );
}