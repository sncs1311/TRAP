CREATE TABLE IF NOT EXISTS transactions (
    txn_id        TEXT PRIMARY KEY,
    card_id       TEXT NOT NULL,
    ts_ms         BIGINT NOT NULL,
    amount        DOUBLE PRECISION NOT NULL,
    features      JSONB NOT NULL,
    score         REAL NOT NULL,
    decision      TEXT NOT NULL CHECK (decision IN ('approve', 'review', 'decline')),
    model_version TEXT NOT NULL,
    latency_ms    REAL,
    source        TEXT NOT NULL DEFAULT 'stream',
    true_label    SMALLINT,          -- simulator ground truth (demo only)
    pattern       TEXT,              -- simulator attack pattern (demo only)
    scored_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_txn_scored_at ON transactions (scored_at DESC);
CREATE INDEX IF NOT EXISTS idx_txn_card      ON transactions (card_id, ts_ms DESC);

CREATE TABLE IF NOT EXISTS fraud_alerts (
    alert_id   BIGSERIAL PRIMARY KEY,
    txn_id     TEXT NOT NULL UNIQUE REFERENCES transactions (txn_id) ON DELETE CASCADE,
    card_id    TEXT NOT NULL,
    score      REAL NOT NULL,
    decision   TEXT NOT NULL,
    reasons    JSONB NOT NULL DEFAULT '[]',
    shap       JSONB NOT NULL DEFAULT '[]',
    status     TEXT NOT NULL DEFAULT 'open'
               CHECK (status IN ('open', 'confirmed_fraud', 'false_positive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alert_status ON fraud_alerts (status, created_at DESC);

CREATE TABLE IF NOT EXISTS analyst_feedback (
    feedback_id BIGSERIAL PRIMARY KEY,
    txn_id      TEXT NOT NULL REFERENCES transactions (txn_id) ON DELETE CASCADE,
    label       TEXT NOT NULL CHECK (label IN ('fraud', 'false_positive')),
    analyst     TEXT NOT NULL DEFAULT 'analyst',
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS psi_snapshots (
    snapshot_id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    feature     TEXT NOT NULL,            -- feature name, 'score', or '__overall__'
    psi         DOUBLE PRECISION NOT NULL,
    status      TEXT NOT NULL,
    n_samples   INT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_psi_time ON psi_snapshots (captured_at DESC, feature);