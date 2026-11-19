"use client";
import { useState } from "react";
import AlertQueue from "@/components/AlertQueue";
import ControlPanel from "@/components/ControlPanel";
import DriftPanel from "@/components/DriftPanel";
import Header from "@/components/Header";
import KpiTiles from "@/components/KpiTiles";
import LiveFeed from "@/components/LiveFeed";
import ShapInspector from "@/components/ShapInspector";
import {
  SCORING, SIM, getJson, postJson,
  type Alert, type Drift, type DriftPoint, type Metrics, type SimStatus, type Stats, type Txn,
} from "@/lib/api";
import { usePoll } from "@/lib/usePoll";

export default function Home() {
  const metrics = usePoll(() => getJson<Metrics>(`${SCORING}/metrics`), 1000);
  const stats = usePoll(() => getJson<Stats>(`${SCORING}/stats`), 2000);
  const feed = usePoll(() => getJson<{ items: Txn[] }>(`${SCORING}/transactions?limit=40`), 1000);
  const alerts = usePoll(() => getJson<{ items: Alert[] }>(`${SCORING}/alerts?status=open&limit=50`), 2000);
  const drift = usePoll(() => getJson<Drift>(`${SCORING}/drift`), 2000);
  const history = usePoll(
    () => getJson<{ points: DriftPoint[] }>(`${SCORING}/drift/history?feature=__overall__&minutes=30`),
    5000,
  );
  const sim = usePoll(() => getJson<SimStatus>(`${SIM}/status`), 1000);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [handled, setHandled] = useState<Set<string>>(new Set());

  const openAlerts = (alerts.data?.items ?? []).filter((a) => !handled.has(a.txn_id));
  const selected = openAlerts.find((a) => a.txn_id === selectedId) ?? null;

  const onFeedback = async (txnId: string, label: "fraud" | "false_positive") => {
    await postJson(`${SCORING}/alerts/${txnId}/feedback`, { label });
    setHandled((s) => new Set(s).add(txnId));          // optimistic removal
    setSelectedId(null);
    alerts.refresh();
    stats.refresh();
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <Header
        scoringUp={!metrics.error}
        simUp={!sim.error}
        modelVersion={metrics.data?.model.version}
      />
      <main className="mx-auto max-w-[1500px] space-y-4 p-4 lg:p-6">
        <KpiTiles metrics={metrics.data} stats={stats.data} />

        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <div className="grid gap-4 md:grid-cols-2">
              <LiveFeed items={feed.data?.items ?? []} />
              <AlertQueue alerts={openAlerts} selectedId={selectedId} onSelect={setSelectedId} />
            </div>
            <ShapInspector alert={selected} onFeedback={onFeedback} />
          </div>
          <div className="space-y-4">
            <DriftPanel drift={drift.data} history={history.data?.points ?? []} />
            <ControlPanel sim={sim.data} onChanged={sim.refresh} />
          </div>
        </div>
      </main>
    </div>
  );
}