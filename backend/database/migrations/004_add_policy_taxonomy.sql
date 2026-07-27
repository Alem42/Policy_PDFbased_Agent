-- Migration 004: Admin-editable two-level policy taxonomy.
-- Run once against the live database before deploying the new backend code.
-- The table is seeded from code (DEFAULT_TAXONOMY) on first read if left empty.

CREATE TABLE IF NOT EXISTS public.policy_taxonomy (
    id uuid PRIMARY KEY,
    parent text NOT NULL,          -- top-level category label
    child text NOT NULL,           -- leaf subcategory label (documents are tagged with these)
    parent_order int NOT NULL DEFAULT 0,
    child_order int NOT NULL DEFAULT 0,
    source_ref text,               -- authoritative source the parent aligns to
    created_at timestamptz(6) NOT NULL DEFAULT now(),
    updated_at timestamptz(6) NOT NULL DEFAULT now(),
    UNIQUE (parent, child)
);
