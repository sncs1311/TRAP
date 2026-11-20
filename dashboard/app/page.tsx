"use client";
import { useEffect, useState } from "react";
import AlertQueue from "@/components/AlertQueue";
import ControlPanel from "@/components/ControlPanel";
import DriftPanel from "@/components/DriftPanel";
import Header from "@/components/Header";
import KpiTiles from "@/components/KpiTiles";
import LiveFeed from "@/components/LiveFeed";
import Section from "@/components/Section";
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

  // keep something selected so the inspector is never empty
  useEffect(() => {
    if (openAlerts.length === 0) {
      if (selectedId) setSelectedId(null);
    } else if (!selectedId || !openAlerts.some((a) => a.txn_id === selectedId)) {
      setSelectedId(openAlerts[0].txn_id);
    }
  }, [openAlerts, selectedId]);

  const onFeedback = async (txnId: string, label: "fraud" | "false_positive") => {
    await postJson(`${SCORING}/alerts/${txnId}/feedback`, { label });
    setHandled((s) => new Set(s).add(txnId));
    setSelectedId(null);
    alerts.refresh();
    stats.refresh();
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-300">
      <div className="mx-auto max-w-[1400px] px-6 pb-12">
        <Header scoringUp={!metrics.error} simUp={!sim.error} modelVersion={metrics.data?.model.version} />
        <KpiTiles metrics={metrics.data} stats={stats.data} />

        <div className="mt-8 grid gap-x-10 gap-y-10 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0 space-y-10">
            <Section title="alerts" meta={`${stats.data?.alerts.open.toLocaleString() ?? "-"} open`}>
              <div className="grid border border-slate-800 md:h-[460px] md:grid-cols-[320px_minmax(0,1fr)]">
                <div className="max-h-64 overflow-auto border-b border-slate-800 md:max-h-none md:border-b-0 md:border-r">
                  <AlertQueue alerts={openAlerts} selectedId={selectedId} onSelect={setSelectedId} />
                </div>
                <div className="overflow-auto">
                  <ShapInspector alert={selected} onFeedback={onFeedback} />
                </div>
              </div>
            </Section>
            <LiveFeed items={feed.data?.items ?? []} />
          </div>

          <aside className="space-y-10">
            <DriftPanel drift={drift.data} history={history.data?.points ?? []} />
            <ControlPanel sim={sim.data} onChanged={sim.refresh} />
          </aside>
        </div>
      </div>
    </div>
  );
}