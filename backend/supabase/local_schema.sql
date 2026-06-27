CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY,
    original_filename text NOT NULL,
    stored_filename text NOT NULL,
    file_path text NOT NULL UNIQUE,
    file_size bigint NOT NULL,
    sha256 text NOT NULL,
    mime_type text NOT NULL DEFAULT 'application/pdf',
    status text NOT NULL DEFAULT 'uploaded',
    approved boolean NOT NULL DEFAULT true,
    access_level text NOT NULL DEFAULT 'public',
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    error_message text
);

CREATE TABLE IF NOT EXISTS app_users (
    id uuid PRIMARY KEY,
    uid text NOT NULL UNIQUE,
    username text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    role text NOT NULL DEFAULT 'user',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT app_users_role_check CHECK (role IN ('admin', 'user'))
);

CREATE TABLE IF NOT EXISTS document_pages (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number integer NOT NULL,
    text text NOT NULL DEFAULT '',
    char_count integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, page_number)
);

CREATE TABLE IF NOT EXISTS document_metadata (
    document_id uuid PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    title text,
    summary text,
    source_type text,
    source_organisation text,
    country_region text,
    language text,
    year integer,
    publication_date date,
    policy_areas text[] NOT NULL DEFAULT '{}',
    keywords text[] NOT NULL DEFAULT '{}',
    stakeholders text[] NOT NULL DEFAULT '{}',
    implementation_risks text[] NOT NULL DEFAULT '{}',
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    generated_by_model text,
    generated_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index integer NOT NULL,
    page_start integer NOT NULL,
    page_end integer NOT NULL,
    section_title text,
    language text,
    text text NOT NULL,
    token_count integer NOT NULL DEFAULT 0,
    keywords text[] NOT NULL DEFAULT '{}',
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id uuid PRIMARY KEY REFERENCES document_chunks(id) ON DELETE CASCADE,
    embedding vector(384) NOT NULL,
    embedding_model text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    job_type text NOT NULL,
    status text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    error_message text,
    details_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_approved_access ON documents(approved, access_level);
CREATE INDEX IF NOT EXISTS idx_app_users_uid ON app_users(uid);
CREATE INDEX IF NOT EXISTS idx_app_users_username ON app_users(username);
CREATE INDEX IF NOT EXISTS idx_document_pages_document_id ON document_pages(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_metadata_keywords ON document_metadata USING gin(keywords);
CREATE INDEX IF NOT EXISTS idx_document_metadata_policy_areas ON document_metadata USING gin(policy_areas);
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_vector
    ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS approved boolean NOT NULL DEFAULT true;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS access_level text NOT NULL DEFAULT 'public';
ALTER TABLE document_metadata ADD COLUMN IF NOT EXISTS source_organisation text;
ALTER TABLE document_metadata ADD COLUMN IF NOT EXISTS language text;
ALTER TABLE document_metadata ADD COLUMN IF NOT EXISTS publication_date date;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS language text;
