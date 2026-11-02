-- Independent evaluation history, corpus identity and human reviews.
CREATE TABLE IF NOT EXISTS evaluation_settings (
    id int PRIMARY KEY CHECK (id = 1), config jsonb NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS evaluation_corpus_documents (
    corpus_id text NOT NULL, source_id text NOT NULL,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    sha256 text NOT NULL, PRIMARY KEY (corpus_id, source_id)
);
CREATE TABLE IF NOT EXISTS evaluation_runs (
    id uuid PRIMARY KEY, status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','completed','failed','cancelled')),
    requested_by uuid REFERENCES app_users(id) ON DELETE SET NULL,
    config jsonb NOT NULL, snapshot jsonb NOT NULL, cases jsonb NOT NULL,
    results jsonb NOT NULL DEFAULT '{}', metrics jsonb NOT NULL DEFAULT '{}',
    error text, lease_token uuid, lease_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz,
    finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_evaluation_runs_status ON evaluation_runs(status, created_at);
CREATE TABLE IF NOT EXISTS evaluation_reviews (
    run_id uuid NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    case_id text NOT NULL, score int NOT NULL CHECK (score BETWEEN 1 AND 5),
    comment text NOT NULL DEFAULT '', reviewer uuid REFERENCES app_users(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (run_id, case_id)
);
