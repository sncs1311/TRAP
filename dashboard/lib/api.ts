export const SCORING = "http://127.0.0.1:8010";
export const SIM = "http://127.0.0.1:4010";

export type Decision = "approve" | "review" | "decline";
export type AlertStatus = "open" | "confirmed_fraud" | "false_positive";

export interface Txn {
  txn_id: string;
  card_id: string;
  ts_ms: number;
  amount: number;
  score: number;
  decision: Decision;
  latency_ms: number | null;
  source: string;
  true_label: number | null;
  pattern: string | null;
  scored_at: string;
}

export interface Contribution {
  feature: string;
  value: number;
  shap: number;
}
export interface Reason {
  feature: string;
  text: string;
  shap: number;
}
export interface Alert {
  alert_id: number;
  txn_id: string;
  card_id: string;
  score: number;
  decision: Decision;
  reasons: Reason[];
  shap: Contribution[];
  status: AlertStatus;
  created_at: string;
  amount: number;
  ts_ms: number;
  pattern: string | null;
  true_label: number | null;
  latency_ms: number | null;
}

export interface Metrics {
  counters: Record<string, number>;
  throughput_eps: number;
  api_latency_ms: { n: number; p50?: number; p95?: number; p99?: number };
  worker_latency_ms_per_event: { n: number; p50?: number; p95?: number; p99?: number };
  stream: { length: number; pending: number; lag: number | null; dlq_length: number };
  model: { version: string; threshold: number; auc_pr_test: number };
}

export interface Stats {
  alerts: { open: number; confirmed_fraud: number; false_positive: number };
  analyst_precision: number | null;
  last_60s: { approve: number; review: number; decline: number; total: number };
}

export interface FeatureDrift {
  psi: number | null;
  status: string;
  n_samples: number;
}
export interface Drift {
  computed_at: string;
  window_minutes: number;
  n_samples: number;
  overall_psi: number | null;
  status: "stable" | "moderate" | "significant" | "insufficient_data";
  top_drivers: string[];
  thresholds: { moderate: number; significant: number };
  features: Record<string, FeatureDrift>;
}
export interface DriftPoint {
  captured_at: string;
  psi: number;
  status: string;
  n_samples: number;
}

export interface SimStatus {
  running: boolean;
  mode: string;
  rps_target: number;
  rps_effective: number;
  burst: { active: boolean; rps: number; seconds_left: number };
  drift: {
    current: Record<string, number>;
    target: Record<string, number>;
    ramp_seconds: number;
    progress: number;
    active: boolean;
  };
  emitted: number;
  by_pattern: Record<string, number>;
  actual_eps: number;
  backlog: number;
  throttled_ticks: number;
  attacks_launched: number;
  last_error: string | null;
}

export async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

export async function postJson<T = unknown>(url: string, body: unknown = {}): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}