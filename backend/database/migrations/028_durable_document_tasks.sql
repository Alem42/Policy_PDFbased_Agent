-- PostgreSQL is the durable task broker. File bytes stay in document storage.
CREATE TABLE IF NOT EXISTS document_tasks (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    task_type text NOT NULL CHECK (task_type IN ('ingest', 'reembed')),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL CHECK (max_attempts >= 1),
    available_at timestamptz NOT NULL DEFAULT now(),
    worker_id text,
    lease_token uuid,
    lease_expires_at timestamptz,
    heartbeat_at timestamptz,
    last_error text,
    result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_document_tasks_active_document
    ON document_tasks(document_id) WHERE status IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS ix_document_tasks_claim
    ON document_tasks(status, available_at, created_at);
CREATE INDEX IF NOT EXISTS ix_document_tasks_expired
    ON document_tasks(lease_expires_at) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS ix_document_tasks_document
    ON document_tasks(document_id, created_at DESC);

-- A key identifies an upload operation by one administrator, not a file chunk.
CREATE TABLE IF NOT EXISTS document_upload_requests (
    actor_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 128),
    fingerprint text NOT NULL,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    task_id uuid NOT NULL REFERENCES document_tasks(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (actor_id, idempotency_key)
);

-- Recover pre-migration uploads that lost their in-memory queue entries.
INSERT INTO document_tasks (id, document_id, task_type, max_attempts)
SELECT gen_random_uuid(), d.id, 'ingest', 3 FROM documents d
WHERE d.status IN ('uploaded', 'ocr', 'parsed', 'annotated')
    AND NOT EXISTS (
        SELECT 1 FROM document_tasks t
        WHERE t.document_id = d.id AND t.status IN ('queued', 'running')
    )
ON CONFLICT DO NOTHING;
