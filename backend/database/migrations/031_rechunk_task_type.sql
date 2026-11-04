-- Re-chunk stored page text with the current chunk settings, without OCR or LLM metadata.
ALTER TABLE document_tasks DROP CONSTRAINT IF EXISTS document_tasks_task_type_check;
ALTER TABLE document_tasks ADD CONSTRAINT document_tasks_task_type_check
    CHECK (task_type IN ('ingest', 'reembed', 'rechunk'));
