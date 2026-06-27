import { useState } from "react";
import { uploadDocuments } from "../api";

export default function DocumentUpload({ onUploaded, compact = false }) {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    if (!files.length || busy) return;

    const form = event.currentTarget;
    setBusy(true);
    setError("");
    try {
      const uploads = await uploadDocuments(files);
      const documentIds = uploads.map((u) => u.id);
      setFiles([]);
      form.reset();
      await onUploaded(documentIds);
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form className={compact ? "upload-strip" : "upload-box"} onSubmit={handleSubmit}>
        <input
          type="file"
          accept="application/pdf,.pdf"
          multiple
          onChange={(event) => setFiles([...event.target.files])}
        />
        {!compact && (
          <div>
            <strong>Choose PDF files</strong>
            <span>Text-based PDFs work now. OCR can be added later.</span>
          </div>
        )}
        <button className="button primary" disabled={!files.length || busy} type="submit">
          {busy ? "Uploading..." : "Upload PDFs"}
        </button>
      </form>
      {error && <div className="notice error">{error}</div>}
    </>
  );
}
