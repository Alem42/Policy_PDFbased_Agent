import DocumentUpload from "../components/DocumentUpload";
import { formatDate, formatSize } from "../utils/format";

export default function HomePage({
  documents,
  loading,
  user,
  onDocumentsChanged,
  onNavigate,
}) {
  const recentDocuments = documents.slice(0, 5);
  const readyCount = documents.filter((document) => document.status === "ready").length;
  const chunkCount = documents.reduce((total, document) => total + (document.chunk_count || 0), 0);

  return (
    <section className="home-page">
      <div className="hero">
        <p className="eyebrow">Knowledge workspace</p>
        <h1>Policy PDF Manager</h1>
        <p>Upload, inspect, and ask questions across policy documents.</p>
        <div className="hero-actions">
          <button
            className="button primary"
            type="button"
            onClick={() => onNavigate(user ? "library" : "auth")}
          >
            {user ? "Browse documents" : "Log in to browse"}
          </button>
          <button
            className="button ghost"
            type="button"
            disabled={!user}
            onClick={() => onNavigate("chat")}
          >
            Ask a question
          </button>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <span>Total documents</span>
          <strong>{documents.length}</strong>
        </div>
        <div className="stat-card">
          <span>Ready for Q&A</span>
          <strong>{readyCount}</strong>
        </div>
        <div className="stat-card">
          <span>Indexed chunks</span>
          <strong>{chunkCount}</strong>
        </div>
      </div>

      <section className="content-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Library</p>
            <h2>Recent PDFs</h2>
          </div>
          <button className="button ghost" type="button" onClick={() => onNavigate("library")}>
            View all
          </button>
        </div>

        {user?.role === "admin" && <DocumentUpload onUploaded={onDocumentsChanged} />}

        <div className="document-list">
          {!user ? (
            <div className="empty-state">Log in to view the policy document library.</div>
          ) : loading ? (
            <div className="empty-state">Loading documents...</div>
          ) : recentDocuments.length === 0 ? (
            <div className="empty-state">No PDFs uploaded yet.</div>
          ) : (
            recentDocuments.map((document) => (
              <article className="document-row" key={document.id || document.name}>
                <div className="file-icon">PDF</div>
                <div className="document-info">
                  <strong>{document.title || document.name}</strong>
                  <span>{document.name}</span>
                  <span>
                    {formatSize(document.size)} - {document.status || "ready"} -{" "}
                    {formatDate(document.uploaded_at)}
                  </span>
                </div>
              </article>
            ))
          )}
        </div>
      </section>
    </section>
  );
}
