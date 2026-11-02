-- Isolated experiment indexes never replace production Library chunks.
CREATE TABLE IF NOT EXISTS evidence_validation_settings (
    id int PRIMARY KEY CHECK (id=1), config jsonb NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS evaluation_indexes (
    id text PRIMARY KEY, config jsonb NOT NULL, source_snapshot jsonb NOT NULL,
    status text NOT NULL CHECK (status IN ('building','ready','failed')),
    stats jsonb NOT NULL DEFAULT '{}', error text,
    created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
CREATE TABLE IF NOT EXISTS evaluation_index_chunks (
    index_id text NOT NULL REFERENCES evaluation_indexes(id) ON DELETE CASCADE,
    chunk_key text NOT NULL, source_id text NOT NULL, page_start int NOT NULL,
    page_end int NOT NULL, text text NOT NULL, token_count int NOT NULL,
    embedding vector(1024) NOT NULL, PRIMARY KEY(index_id,chunk_key)
);
CREATE TABLE IF NOT EXISTS evaluation_trials (
    run_id uuid NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    variant_id text NOT NULL, case_id text NOT NULL, result jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(run_id,variant_id,case_id)
);
CREATE TABLE IF NOT EXISTS evaluation_artifacts (
    run_id uuid NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    name text NOT NULL, payload jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(run_id,name)
);
