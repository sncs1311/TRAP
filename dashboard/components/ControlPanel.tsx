"use client";
import { useState } from "react";
import { SCORING, SIM, postJson, type SimStatus } from "@/lib/api";
import Section from "./Section";

function Btn({
  children,
  onClick,
  danger,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className={`border px-2.5 py-1 disabled:opacity-40 ${
        danger
          ? "border-red-500/50 text-red-400 hover:bg-red-500/10"
          : "border-slate-700 text-slate-300 hover:bg-slate-800"
      }`}
    >
      {children}
    </button>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[56px_1fr] items-start gap-3 py-2">
      <span className="pt-1 text-slate-600">{label}</span>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

export default function ControlPanel({ sim, onChanged }: { sim: SimStatus | null; onChanged: () => void }) {
  const [msg, setMsg] = useState("");
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
  const meta = sim
    ? `${sim.running ? "running" : "paused"} · ${sim.actual_eps.toFixed(0)} eps · backlog ${sim.backlog}`
    : "simulator unreachable";

  return (
    <Section title="controls" meta={meta}>
      <div className="divide-y divide-slate-900">
        <Row label="traffic">
          <Btn
            disabled={sim?.burst.active}
            onClick={() => run("burst", () => postJson(`${SIM}/control/burst`, { rps: 300, duration_s: 20 }))}
          >
            {sim?.burst.active ? `burst ${sim.burst.seconds_left.toFixed(0)}s left` : "burst 300 rps · 20s"}
          </Btn>
          <Btn onClick={() => run(sim?.running ? "pause" : "resume", () => postJson(`${SIM}/control/${sim?.running ? "stop" : "start"}`))}>
            {sim?.running ? "pause" : "resume"}
          </Btn>
        </Row>

        <Row label="rate">
          <input
            type="number"
            min={0}
            max={2000}
            value={rps}
            onChange={(e) => setRps(Number(e.target.value))}
            className="w-16 border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200"
          />
          <span className="text-slate-600">rps</span>
          <Btn onClick={() => run("rate", () => postJson(`${SIM}/control/rps`, { rps }))}>set</Btn>
        </Row>

        <Row label="attack">
          <Btn danger onClick={() => run("card-testing", () => postJson(`${SIM}/control/attack`, { kind: "card_testing", n_attacks: 3 }))}>
            card testing ×3
          </Btn>
          <Btn danger onClick={() => run("takeover", () => postJson(`${SIM}/control/attack`, { kind: "takeover", n_attacks: 3 }))}>
            takeover ×3
          </Btn>
        </Row>

        <Row label="drift">
          <Btn onClick={() => run("mild drift", () => postJson(`${SIM}/control/drift`, { preset: "mild", ramp_seconds: 30 }))}>mild</Btn>
          <Btn danger onClick={() => run("severe drift", () => postJson(`${SIM}/control/drift`, { preset: "severe", ramp_seconds: 30 }))}>severe</Btn>
          <Btn onClick={() => run("clear drift", () => postJson(`${SIM}/control/drift/clear`, {}))}>clear</Btn>
          {d?.active && <span className="text-amber-400">ramp {(d.progress * 100).toFixed(0)}%</span>}
        </Row>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 text-slate-600">
        <Btn
          onClick={() =>
            run("probe", async () => {
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
          probe /score ×20
        </Btn>
        <span className="truncate">{msg}</span>
      </div>
    </Section>
  );
}