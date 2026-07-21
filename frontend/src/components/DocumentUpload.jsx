import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Collapse,
  IconButton,
  LinearProgress,
  Typography,
} from "@mui/material";
import { styled } from "@mui/material/styles";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import CloseIcon from "@mui/icons-material/Close";
import { getDocumentDetail, getProcessingStatus, uploadDocuments } from "../api";

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

const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md"];

const TERMINAL_STATUSES = new Set(["indexed", "ready", "failed"]);

const STATUS_META = {
  queued: { label: "Queued", color: "default" },
  extracting: { label: "Extracting", color: "info" },
  chunking: { label: "Chunking", color: "info" },
  embedding: { label: "Embedding", color: "info" },
  indexed: { label: "Indexed", color: "success" },
  ready: { label: "Indexed", color: "success" },
  failed: { label: "Failed", color: "error" },
};

// How long to keep polling a single upload batch before giving up.
const POLL_MAX_ATTEMPTS = 40; // ~2 minutes at 3s intervals
const POLL_INTERVAL_MS = 3000;

// How long an "Indexed" row stays visible before auto-dismissing, unless
// the user has hovered or clicked it (see pinned/onMouseEnter below).
const AUTO_DISMISS_DELAY_MS = 6000;

function ParsedFields({ detail }) {
  return (
    <Box component="dl" sx={{ display: "grid", gap: 1, m: 0, py: 1.5 }}>
      <Box>
        <Typography component="dt" variant="caption" sx={{ fontWeight: 800, color: "#64716b" }}>
          Title
        </Typography>
        <Typography component="dd" variant="body2" sx={{ m: 0 }}>
          {detail.title || detail.name}
        </Typography>
      </Box>
      {detail.summary && (
        <Box>
          <Typography component="dt" variant="caption" sx={{ fontWeight: 800, color: "#64716b" }}>
            Summary
          </Typography>
          <Typography component="dd" variant="body2" sx={{ m: 0, color: "#63706a" }}>
            {detail.summary}
          </Typography>
        </Box>
      )}
      <Box sx={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
        <Box>
          <Typography component="dt" variant="caption" sx={{ fontWeight: 800, color: "#64716b" }}>
            Source organisation
          </Typography>
          <Typography component="dd" variant="body2" sx={{ m: 0 }}>
            {detail.source_organisation || "Unknown"}
          </Typography>
        </Box>
        <Box>
          <Typography component="dt" variant="caption" sx={{ fontWeight: 800, color: "#64716b" }}>
            Region
          </Typography>
          <Typography component="dd" variant="body2" sx={{ m: 0 }}>
            {detail.country_region || "Unknown"}
          </Typography>
        </Box>
        <Box>
          <Typography component="dt" variant="caption" sx={{ fontWeight: 800, color: "#64716b" }}>
            Pages / Chunks
          </Typography>
          <Typography component="dd" variant="body2" sx={{ m: 0 }}>
            {detail.page_count ?? 0} / {detail.chunk_count ?? 0}
          </Typography>
        </Box>
      </Box>
      {(detail.policy_areas || []).length > 0 && (
        <Box>
          <Typography component="dt" variant="caption" sx={{ fontWeight: 800, color: "#64716b" }}>
            Policy areas
          </Typography>
          <Typography component="dd" sx={{ m: 0 }}>
            {detail.policy_areas.map((area) => (
              <Chip key={area} label={area} size="small" sx={{ mr: 0.5, mt: 0.5 }} />
            ))}
          </Typography>
        </Box>
      )}
    </Box>
  );
}

function UploadJobRow({ job, onToggle, onDismiss, onMouseEnter, onMouseLeave }) {
  const meta = STATUS_META[job.status] || STATUS_META.queued;
  const isTerminal = TERMINAL_STATUSES.has(job.status);
  const canExpand = job.status !== "failed" && !!job.detail;

  return (
    <Box
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      sx={{
        border: "1px solid rgba(201, 204, 196, 0.92)",
        borderRadius: "8px",
        background: "#fff",
        overflow: "hidden",
      }}
    >
      <Box
        onClick={canExpand ? onToggle : undefined}
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          p: 1.25,
          cursor: canExpand ? "pointer" : "default",
        }}
      >
        <Typography
          variant="body2"
          sx={{ fontWeight: 700, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        >
          {job.filename}
        </Typography>
        <Chip label={meta.label} color={meta.color} size="small" />
        {canExpand && (
          <IconButton
            size="small"
            onClick={(event) => {
              event.stopPropagation();
              onToggle();
            }}
            aria-label="Toggle parsed fields"
          >
            {job.expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
          </IconButton>
        )}
        {isTerminal && (
          <IconButton
            size="small"
            onClick={(event) => {
              event.stopPropagation();
              onDismiss();
            }}
            aria-label="Dismiss"
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        )}
      </Box>
      {!isTerminal && <LinearProgress variant="indeterminate" />}
      {job.status === "failed" && job.error && (
        <Alert severity="error" sx={{ borderRadius: 0 }}>
          {job.error}
        </Alert>
      )}
      {canExpand && (
        <Collapse in={job.expanded}>
          <Box sx={{ px: 1.25, pb: 0.5, borderTop: "1px solid rgba(201, 204, 196, 0.6)" }}>
            <ParsedFields detail={job.detail} />
          </Box>
        </Collapse>
      )}
    </Box>
  );
}

export default function DocumentUpload({ onUploaded, compact = false }) {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState([]);
  const cancelledRefs = useRef([]);
  const dismissTimersRef = useRef(new Map());
  const hoveredJobIdsRef = useRef(new Set());

  useEffect(
    () => () => {
      cancelledRefs.current.forEach((ref) => {
        ref.current = true;
      });
      dismissTimersRef.current.forEach((timerId) => window.clearTimeout(timerId));
      dismissTimersRef.current.clear();
      hoveredJobIdsRef.current.clear();
    },
    [],
  );

  function cancelAutoDismiss(jobId) {
    const timerId = dismissTimersRef.current.get(jobId);
    if (timerId) {
      window.clearTimeout(timerId);
      dismissTimersRef.current.delete(jobId);
    }
  }

  function scheduleAutoDismiss(jobId) {
    cancelAutoDismiss(jobId);
    const timerId = window.setTimeout(() => {
      dismissTimersRef.current.delete(jobId);
      dismissJob(jobId);
    }, AUTO_DISMISS_DELAY_MS);
    dismissTimersRef.current.set(jobId, timerId);
  }

  // Start the auto-dismiss countdown the moment a row first reaches a
  // successful terminal state, as long as it hasn't been pinned by a click.
  // Re-runs on every `jobs` update (e.g. the parsed-fields fetch completing
  // shortly after "indexed"), so it must also skip rows currently hovered --
  // otherwise a later update would blindly re-schedule a fresh countdown
  // right out from under an in-progress hover.
  useEffect(() => {
    jobs.forEach((job) => {
      const isSuccess = job.status === "indexed" || job.status === "ready";
      if (
        isSuccess &&
        !job.pinned &&
        !hoveredJobIdsRef.current.has(job.id) &&
        !dismissTimersRef.current.has(job.id)
      ) {
        scheduleAutoDismiss(job.id);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs]);

  function selectFiles(fileList) {
    setFiles(
      Array.from(fileList).filter((file) =>
        ACCEPTED_EXTENSIONS.some((extension) => file.name.toLowerCase().endsWith(extension)),
      ),
    );
  }

  function removeFile(indexToRemove) {
    setFiles((current) => current.filter((_, index) => index !== indexToRemove));
  }

  function toggleJob(jobId) {
    cancelAutoDismiss(jobId);
    setJobs((current) =>
      current.map((job) =>
        job.id === jobId ? { ...job, expanded: !job.expanded, pinned: true } : job,
      ),
    );
  }

  function dismissJob(jobId) {
    cancelAutoDismiss(jobId);
    setJobs((current) => current.filter((job) => job.id !== jobId));
  }

  function handleRowMouseEnter(jobId) {
    hoveredJobIdsRef.current.add(jobId);
    cancelAutoDismiss(jobId);
  }

  function handleRowMouseLeave(jobId) {
    hoveredJobIdsRef.current.delete(jobId);
    const job = jobs.find((item) => item.id === jobId);
    const isSuccess = job && (job.status === "indexed" || job.status === "ready");
    if (isSuccess && !job.pinned) {
      scheduleAutoDismiss(jobId);
    }
  }

  async function pollBatch(jobIds, cancelledRef) {
    let lastResults = [];
    for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt += 1) {
      if (cancelledRef.current) return;
      await new Promise((resolve) => setTimeout(resolve, attempt === 0 ? 0 : POLL_INTERVAL_MS));
      if (cancelledRef.current) return;

      lastResults = await Promise.all(
        jobIds.map(async (id) => {
          try {
            return { id, ...(await getProcessingStatus(id)) };
          } catch {
            return null;
          }
        }),
      );
      if (cancelledRef.current) return;

      setJobs((current) =>
        current.map((job) => {
          const result = lastResults.find((r) => r && r.id === job.id);
          return result ? { ...job, status: result.status, error: result.error } : job;
        }),
      );

      const stillPending = lastResults.some((r) => !r || !TERMINAL_STATUSES.has(r.status));
      if (!stillPending) break;
    }

    const indexedIds = lastResults
      .filter((r) => r && (r.status === "indexed" || r.status === "ready"))
      .map((r) => r.id);

    await Promise.all(
      indexedIds.map(async (id) => {
        try {
          const detail = await getDocumentDetail(id);
          if (cancelledRef.current) return;
          setJobs((current) => current.map((job) => (job.id === id ? { ...job, detail } : job)));
        } catch {
          // Parsed fields just won't be shown for this row; status still reflects "Indexed".
        }
      }),
    );
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!files.length || busy) return;

    const form = event.currentTarget;
    const pendingFiles = files;
    setBusy(true);
    setError("");
    try {
      const uploads = await uploadDocuments(pendingFiles);
      const newJobs = uploads.map((upload, index) => ({
        id: upload.id,
        filename: pendingFiles[index]?.name || upload.id,
        status: upload.processing_status || "queued",
        error: null,
        detail: null,
        expanded: false,
        pinned: false,
      }));
      setJobs((current) => [...newJobs, ...current]);
      setFiles([]);
      form.reset();

      const cancelledRef = { current: false };
      cancelledRefs.current.push(cancelledRef);
      const jobIds = newJobs.map((job) => job.id);
      pollBatch(jobIds, cancelledRef)
        .then(() => (cancelledRef.current ? null : onUploaded(jobIds)))
        .catch(() => {
          // Background polling/refresh failure -- the row statuses already
          // reflect the last known state, nothing further to surface here.
        });
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
            Browse Documents
            <VisuallyHiddenInput
              type="file"
              accept="application/pdf,.pdf,.docx,.txt,.md"
              multiple
              onChange={(event) => {
                selectFiles(event.target.files);
                event.target.value = "";
              }}
            />
          </Button>
          <Box sx={{ minWidth: 0 }}>
            <Typography component="strong" sx={{ display: "block", fontWeight: 700 }}>
              {files.length ? `${files.length} file${files.length === 1 ? "" : "s"} selected` : "Drop files here"}
            </Typography>
            {!compact && (
              <Typography variant="body2" sx={{ color: "text.secondary" }} noWrap>
                {files.length
                  ? files.map((file) => file.name).join(", ")
                  : "PDF, Word (.docx), TXT, or Markdown."}
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
          {busy ? "Uploading..." : "Upload Documents"}
        </Button>
        {files.length > 0 && (
          <Box
            aria-label="Selected files"
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
      {jobs.length > 0 && (
        <Box aria-label="Upload progress" sx={{ display: "grid", gap: 1, mb: "18px" }}>
          {jobs.map((job) => (
            <UploadJobRow
              key={job.id}
              job={job}
              onToggle={() => toggleJob(job.id)}
              onDismiss={() => dismissJob(job.id)}
              onMouseEnter={() => handleRowMouseEnter(job.id)}
              onMouseLeave={() => handleRowMouseLeave(job.id)}
            />
          ))}
        </Box>
      )}
    </>
  );
}
