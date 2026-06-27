import { useMemo, useState } from "react";
import {
  deleteDocument,
  getDocumentChunks,
  getDocumentDetail,
  openDocumentFile,
  updateDocument,
} from "../api";
import DocumentDrawer from "../components/DocumentDrawer";
import DocumentUpload from "../components/DocumentUpload";
import { asText, formatDate, formatSize } from "../utils/format";

export default function LibraryPage({
  documents,
  loading,
  user,
  onRefresh,
  onRescan,
  onDocumentsChanged,
}) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [areaFilter, setAreaFilter] = useState("all");
  const [regionFilter, setRegionFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sortBy, setSortBy] = useState("uploaded_desc");
  const [selected, setSelected] = useState(null);
  const [chunks, setChunks] = useState(null);
  const [openChunkId, setOpenChunkId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const policyAreas = useMemo(
    () =>
      [...new Set(documents.flatMap((document) => document.policy_areas || []))]
        .filter(Boolean)
        .sort(),
    [documents],
  );
  const regions = useMemo(
    () =>
      [...new Set(documents.map((document) => document.country_region))]
        .filter(Boolean)
        .sort(),
    [documents],
  );
  const sourceTypes = useMemo(
    () =>
      [...new Set(documents.map((document) => document.source_type))]
        .filter(Boolean)
        .sort(),
    [documents],
  );

  const filteredDocuments = useMemo(() => {
    const cleanQuery = query.trim().toLowerCase();
    const filtered = documents.filter((document) => {
      const searchText = [
        document.name,
        document.title,
        document.summary,
        document.country_region,
        document.source_type,
        document.year,
        asText(document.policy_areas),
        asText(document.keywords),
      ]
        .join(" ")
        .toLowerCase();

      return (
        (!cleanQuery || searchText.includes(cleanQuery)) &&
        (statusFilter === "all" || document.status === statusFilter) &&
        (areaFilter === "all" || (document.policy_areas || []).includes(areaFilter)) &&
        (regionFilter === "all" || document.country_region === regionFilter) &&
        (typeFilter === "all" || document.source_type === typeFilter)
      );
    });

    return [...filtered].sort((first, second) => {
      if (sortBy === "name_asc") return first.name.localeCompare(second.name);
      if (sortBy === "year_desc") return (second.year || 0) - (first.year || 0);
      if (sortBy === "chunks_desc") return (second.chunk_count || 0) - (first.chunk_count || 0);
      return (second.modified_at || 0) - (first.modified_at || 0);
    });
  }, [areaFilter, documents, query, regionFilter, sortBy, statusFilter, typeFilter]);

  async function handleDelete(document) {
    if (!window.confirm(`Delete "${document.name}"?`)) return;
    setBusy(true);
    setError("");
    try {
      await deleteDocument(document.id);
      if (selected?.id === document.id) closeDrawer();
      await onDocumentsChanged();
    } catch (deleteError) {
      setError(deleteError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleOpenSource(document) {
    setBusy(true);
    setError("");
    try {
      await openDocumentFile(document.id);
    } catch (sourceError) {
      setError(sourceError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleGovernanceUpdate(document, updates) {
    setBusy(true);
    setError("");
    try {
      await updateDocument(document.id, updates);
      await onDocumentsChanged();
    } catch (updateError) {
      setError(updateError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDetail(document) {
    setBusy(true);
    setError("");
    try {
      setSelected(await getDocumentDetail(document.id));
      setChunks(null);
      setOpenChunkId(null);
    } catch (detailError) {
      setError(detailError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleChunks(document) {
    setBusy(true);
    setError("");
    try {
      setSelected(await getDocumentDetail(document.id));
      setChunks(await getDocumentChunks(document.id));
      setOpenChunkId(null);
    } catch (chunkError) {
      setError(chunkError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRescan() {
    setBusy(true);
    setError("");
    try {
      await onRescan();
      closeDrawer();
    } catch (rescanError) {
      setError(rescanError.message);
    } finally {
      setBusy(false);
    }
  }

  function closeDrawer() {
    setSelected(null);
    setChunks(null);
    setOpenChunkId(null);
  }

  return (
    <section className="page-stack">
      <div className="page-heading split-heading">
        <div>
          <p className="eyebrow">Policy library</p>
          <h1>PDF Management</h1>
          <p>Manage uploaded documents, inspect metadata, and review retrieval chunks.</p>
        </div>
        <div className="heading-actions">
          <button className="button ghost" disabled={busy} type="button" onClick={onRefresh}>
            Refresh
          </button>
          {user?.role === "admin" && (
            <button className="button primary" disabled={busy} type="button" onClick={handleRescan}>
              {busy ? "Working..." : "Rescan files"}
            </button>
          )}
        </div>
      </div>

      {user?.role === "admin" && <DocumentUpload compact onUploaded={onDocumentsChanged} />}

      <div className="filter-bar">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search filename, title, region, policy area, keywords"
        />
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="all">All statuses</option>
          <option value="ready">Ready</option>
          <option value="failed">Failed</option>
          <option value="uploaded">Uploaded</option>
          <option value="parsed">Parsed</option>
          <option value="annotated">Annotated</option>
        </select>
        <select value={areaFilter} onChange={(event) => setAreaFilter(event.target.value)}>
          <option value="all">All policy areas</option>
          {policyAreas.map((area) => (
            <option key={area} value={area}>
              {area}
            </option>
          ))}
        </select>
        <select value={regionFilter} onChange={(event) => setRegionFilter(event.target.value)}>
          <option value="all">All regions</option>
          {regions.map((region) => (
            <option key={region} value={region}>
              {region}
            </option>
          ))}
        </select>
        <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
          <option value="all">All source types</option>
          {sourceTypes.map((sourceType) => (
            <option key={sourceType} value={sourceType}>
              {sourceType}
            </option>
          ))}
        </select>
        <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
          <option value="uploaded_desc">Newest first</option>
          <option value="name_asc">Filename A-Z</option>
          <option value="year_desc">Year desc</option>
          <option value="chunks_desc">Most chunks</option>
        </select>
      </div>

      {error && <div className="notice error">{error}</div>}

      <section className="document-table">
        <div className="table-head">
          <span>Document</span>
          <span>Metadata</span>
          <span>Processing</span>
          <span>Actions</span>
        </div>
        {loading ? (
          <div className="empty-state">Loading documents...</div>
        ) : filteredDocuments.length === 0 ? (
          <div className="empty-state">No matching PDFs.</div>
        ) : (
          filteredDocuments.map((document) => (
            <article className="table-row" key={document.id}>
              <div className="document-cell">
                <strong>{document.title || document.name}</strong>
                <span>{document.name}</span>
                <span>
                  {formatSize(document.size)} - {formatDate(document.uploaded_at)}
                </span>
              </div>
              <div className="metadata-cell">
                <span>{document.country_region || "Unknown region"}</span>
                <span>{document.source_type || "Unclassified source"}</span>
                <span>{document.source_organisation || "Unknown organisation"}</span>
                <span>{document.language || "Unknown language"}</span>
                <div className="tag-list">
                  {(document.policy_areas || []).slice(0, 3).map((area) => (
                    <small key={area}>{area}</small>
                  ))}
                </div>
              </div>
              <div className="processing-cell">
                <strong className={`status-text status-${document.status}`}>
                  {document.status || "unknown"}
                </strong>
                <span>{document.page_count || 0} pages</span>
                <span>{document.chunk_count || 0} chunks</span>
                {user?.role === "admin" && (
                  <span>
                    {document.approved ? "approved" : "not approved"} / {document.access_level}
                  </span>
                )}
              </div>
              <div className="row-actions">
                {["uploaded", "parsed", "annotated"].includes(document.status) && (
                  <small style={{ color: "#999" }}>
                    {document.status === "uploaded" && "uploading..."}
                    {document.status === "parsed" && "parsing..."}
                    {document.status === "annotated" && "analysing..."}
                  </small>
                )}
                {document.status === "failed" && (
                  <small style={{ color: "#d00" }}>failed</small>
                )}
                <button className="button ghost" type="button" onClick={() => handleDetail(document)}>
                  Details
                </button>
                <button
                  className="button ghost"
                  type="button"
                  onClick={() => handleChunks(document)}
                  disabled={document.status !== "ready"}
                  title={document.status !== "ready" ? "Document still processing" : ""}
                >
                  Chunks
                </button>
                <button className="button ghost" type="button" onClick={() => handleOpenSource(document)}>
                  Source
                </button>
                {user?.role === "admin" && (
                  <>
                    <button
                      className="button ghost"
                      type="button"
                      onClick={() =>
                        handleGovernanceUpdate(document, { approved: !document.approved })
                      }
                    >
                      {document.approved ? "Unapprove" : "Approve"}
                    </button>
                    <button
                      className="button ghost"
                      type="button"
                      onClick={() =>
                        handleGovernanceUpdate(document, {
                          access_level:
                            document.access_level === "public" ? "private" : "public",
                        })
                      }
                    >
                      {document.access_level === "public" ? "Make private" : "Make public"}
                    </button>
                    <button className="button danger" type="button" onClick={() => handleDelete(document)}>
                      Delete
                    </button>
                  </>
                )}
              </div>
            </article>
          ))
        )}
      </section>

      <DocumentDrawer
        detail={selected}
        chunks={chunks}
        openChunkId={openChunkId}
        onToggleChunk={(chunkId) => setOpenChunkId(openChunkId === chunkId ? null : chunkId)}
        onClose={closeDrawer}
      />
    </section>
  );
}
