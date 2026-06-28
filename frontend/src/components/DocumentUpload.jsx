import { useState } from "react";
import { Alert, Box, Button, Chip, Typography } from "@mui/material";
import { styled } from "@mui/material/styles";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import { uploadDocuments } from "../api";

const VisuallyHiddenInput = styled("input")({
  clip: "rect(0 0 0 0)",
  clipPath: "inset(50%)",
  height: 1,
  overflow: "hidden",
  position: "absolute",
  bottom: 0,
  left: 0,
  whiteSpace: "nowrap",
  width: 1,
});

export default function DocumentUpload({ onUploaded, compact = false }) {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function selectFiles(fileList) {
    setFiles(
      Array.from(fileList).filter(
        (file) => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"),
      ),
    );
  }

  function removeFile(indexToRemove) {
    setFiles((current) => current.filter((_, index) => index !== indexToRemove));
  }

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
      <Box
        component="form"
        onSubmit={handleSubmit}
        sx={
          compact
            ? {
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr) auto",
                gap: "12px",
                alignItems: "center",
                mb: "14px",
                p: 2,
                border: "1px solid rgba(201, 204, 196, 0.92)",
                borderRadius: "8px",
                background: "rgba(255, 255, 255, 0.86)",
                boxShadow: "0 14px 42px rgba(47, 57, 51, 0.06)",
              }
            : {
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr) auto",
                gap: "12px",
                alignItems: "center",
                mb: "18px",
                p: 2,
                border: "1px dashed #b4beb7",
                borderRadius: "8px",
                background: "#fbfcfa",
              }
        }
      >
        <Box
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            selectFiles(event.dataTransfer.files);
          }}
          sx={{ display: "flex", alignItems: "center", gap: 1.5, minWidth: 0 }}
        >
          <Button component="label" variant="outlined" startIcon={<CloudUploadIcon />} disabled={busy}>
            Browse PDFs
            <VisuallyHiddenInput
              type="file"
              accept="application/pdf,.pdf"
              multiple
              onChange={(event) => {
                selectFiles(event.target.files);
                event.target.value = "";
              }}
            />
          </Button>
          <Box sx={{ minWidth: 0 }}>
            <Typography component="strong" sx={{ display: "block", fontWeight: 700 }}>
              {files.length ? `${files.length} PDF${files.length === 1 ? "" : "s"} selected` : "Drop PDF files here"}
            </Typography>
            {!compact && (
              <Typography variant="body2" sx={{ color: "text.secondary" }} noWrap>
                {files.length ? files.map((file) => file.name).join(", ") : "Text-based PDFs work best."}
              </Typography>
            )}
          </Box>
        </Box>
        <Button
          variant="contained"
          disabled={!files.length || busy}
          type="submit"
          startIcon={<CloudUploadIcon />}
        >
          {busy ? "Uploading..." : "Upload PDFs"}
        </Button>
        {files.length > 0 && (
          <Box
            aria-label="Selected PDF files"
            sx={{
              gridColumn: "1 / -1",
              display: "flex",
              flexWrap: "wrap",
              gap: 1,
              pt: 0.5,
            }}
          >
            {files.map((file, index) => (
              <Chip
                key={`${file.name}-${file.size}-${file.lastModified}-${index}`}
                label={file.name}
                variant="outlined"
                disabled={busy}
                onDelete={() => removeFile(index)}
                sx={{ maxWidth: "100%", "& .MuiChip-label": { overflow: "hidden", textOverflow: "ellipsis" } }}
              />
            ))}
          </Box>
        )}
      </Box>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
    </>
  );
}
