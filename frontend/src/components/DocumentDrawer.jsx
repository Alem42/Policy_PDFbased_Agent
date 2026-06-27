export default function DocumentDrawer({ detail, chunks, openChunkId, onToggleChunk, onClose }) {
  if (!detail) return null;

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <p className="eyebrow">{chunks ? "Document chunks" : "Document record"}</p>
            <h2>{detail.title || detail.name}</h2>
          </div>
          <button className="icon-button" type="button" aria-label="Close details" onClick={onClose}>
            x
          </button>
        </div>

        <dl className="metadata-list">
          <div>
            <dt>Filename</dt>
            <dd>{detail.name}</dd>
          </div>
          <div>
            <dt>Region</dt>
            <dd>{detail.country_region || "Unknown"}</dd>
          </div>
          <div>
            <dt>Year</dt>
            <dd>{detail.year || "Unknown"}</dd>
          </div>
          <div>
            <dt>Source type</dt>
            <dd>{detail.source_type || "Unknown"}</dd>
          </div>
          <div>
            <dt>Source organisation</dt>
            <dd>{detail.source_organisation || "Unknown"}</dd>
          </div>
          <div>
            <dt>Language</dt>
            <dd>{detail.language || "Unknown"}</dd>
          </div>
          <div>
            <dt>Publication date</dt>
            <dd>{detail.publication_date || "Unknown"}</dd>
          </div>
          <div>
            <dt>Access</dt>
            <dd>
              {detail.approved ? "Approved" : "Not approved"} / {detail.access_level || "public"}
            </dd>
          </div>
          <div>
            <dt>Policy areas</dt>
            <dd>{(detail.policy_areas || []).join(", ") || "None"}</dd>
          </div>
          <div>
            <dt>Keywords</dt>
            <dd>{(detail.keywords || []).join(", ") || "None"}</dd>
          </div>
        </dl>

        {detail.summary && <p className="drawer-summary">{detail.summary}</p>}

        <details className="json-details">
          <summary>Metadata JSON</summary>
          <pre>{JSON.stringify(detail.metadata_json || {}, null, 2)}</pre>
        </details>

        {chunks && (
          <div className="chunk-list">
            <p className="eyebrow">Chunks</p>
            {chunks.chunks.map((chunk) => (
              <article className="chunk-row" key={chunk.id}>
                <button type="button" onClick={() => onToggleChunk(chunk.id)}>
                  Chunk {chunk.chunk_index} - pages {chunk.page_start}
                  {chunk.page_end !== chunk.page_start ? `-${chunk.page_end}` : ""} -{" "}
                  {chunk.token_count} tokens
                  {chunk.language ? ` - ${chunk.language}` : ""}
                </button>
                {openChunkId === chunk.id && (
                  <div>
                    <pre>{chunk.text}</pre>
                    <details>
                      <summary>Chunk metadata</summary>
                      <pre>
                        {JSON.stringify(
                          {
                            id: chunk.id,
                            embedding_model: chunk.embedding_model,
                            metadata_json: chunk.metadata_json,
                            keywords: chunk.keywords,
                          },
                          null,
                          2,
                        )}
                      </pre>
                    </details>
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}
