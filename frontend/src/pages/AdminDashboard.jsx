import DocumentUpload from "../components/DocumentUpload";
import { formatDate, formatSize } from "../utils/format";

export default function AdminDashboard({
  documents,
  loading,
  user,
  onDocumentsChanged,
  onNavigate,
}) {
  // require admin login
  if (!user) {
    return (
      <section className="home-page">
        <div className="empty-state">
          <p>Access Denied. Administrator privileges required.</p>
          <button className="button primary" onClick={() => onNavigate("auth")}>Go to Login</button>
        </div>
      </section>
    );
  }

  const readyCount = documents.filter((document) => document.status === "ready").length;
  const chunkCount = documents.reduce((total, document) => total + (document.chunk_count || 0), 0);

  return (
    <section className="home-page admin-dashboard">
      <div className="hero">
        <p className="eyebrow">Admin Workspace</p>
        <h1>Knowledge Base Management</h1>
        <p>Manage policy documents, upload new PDFs, and monitor indexing status.</p>
        <div className="hero-actions">
          <button
            className="button ghost"
            type="button"
            onClick={() => onNavigate("chat")}
          >
            ← Back to Q&A
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
            <h2>All Documents</h2>
          </div>
        </div>

        <DocumentUpload onUploaded={onDocumentsChanged} />

        <div className="document-list">
          {loading ? (
            <div className="empty-state">Loading documents...</div>
          ) : documents.length === 0 ? (
            <div className="empty-state">No PDFs uploaded yet.</div>
          ) : (
            documents.map((document) => (
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
                {/* TODO: Delete and Edit */}
              </article>
            ))
          )}
        </div>
      </section>
    </section>
  );
}