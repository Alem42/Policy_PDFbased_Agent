import { useEffect, useState } from "react";
import { Alert, Box, Button, LinearProgress, Typography } from "@mui/material";
import { getTaskProgress } from "../api";

// One library-wide batch (rescan, re-embed or re-chunk) at a time, remembered per
// browser so the bar survives a page reload while workers are still processing.
const STORAGE_KEY = "libraryTaskBatch";

export function rememberLibraryBatch(kind, taskIds) {
  const batch = { kind, taskIds, startedAt: new Date().toISOString() };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(batch));
  } catch {
    // Storage unavailable: the bar still shows until the page is left.
  }
  window.dispatchEvent(new CustomEvent("library-batch-started", { detail: batch }));
  return batch;
}

function loadBatch() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
  } catch {
    return null;
  }
}

const LABELS = {
  rechunk: "Re-chunking and re-embedding",
  reembed: "Re-embedding",
  rescan: "Rescanning",
};

export default function LibraryTaskProgress() {
  const [batch, setBatch] = useState(loadBatch);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const onStart = (event) => {
      setBatch(event.detail);
      setProgress(null);
      setError("");
    };
    window.addEventListener("library-batch-started", onStart);
    return () => window.removeEventListener("library-batch-started", onStart);
  }, []);

  useEffect(() => {
    if (!batch?.taskIds?.length) return undefined;
    let stopped = false;
    let timer;
    async function poll() {
      try {
        const value = await getTaskProgress(batch.taskIds);
        if (stopped) return;
        setProgress(value);
        setError("");
        if (!value.finished) timer = setTimeout(poll, 2000);
      } catch (pollError) {
        if (stopped) return;
        setError(pollError.message);
        timer = setTimeout(poll, 5000);
      }
    }
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [batch]);

  function dismiss() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Nothing to clear.
    }
    setBatch(null);
    setProgress(null);
  }

  if (!batch) return null;
  const total = progress?.total ?? batch.taskIds.length;
  const done = (progress?.succeeded ?? 0) + (progress?.failed ?? 0);
  const percent = total ? Math.round((done / total) * 100) : 100;
  const finished = progress?.finished;

  return (
    <Box sx={{ mt: 2, p: 2, border: "1px solid #e2e5df", borderRadius: 2, display: "grid", gap: 1 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Typography variant="body2" sx={{ fontWeight: 800, color: "#214f42" }}>
          {LABELS[batch.kind] || "Processing"} · {done} / {total} documents
        </Typography>
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          {finished
            ? "Finished"
            : `${progress?.running ?? 0} running · ${progress?.queued ?? total} waiting`}
        </Typography>
        <Box sx={{ flex: 1 }} />
        {finished && <Button size="small" onClick={dismiss}>Dismiss</Button>}
      </Box>
      <LinearProgress
        variant={progress ? "determinate" : "indeterminate"}
        value={percent}
        color={progress?.failed ? "warning" : "primary"}
        sx={{ height: 8, borderRadius: 999 }}
      />
      {progress?.failed > 0 && (
        <Alert severity="warning">
          {progress.failed} document(s) failed. {progress.errors?.map((e) => `${e.error} (${e.n})`).join(" · ")}
        </Alert>
      )}
      {error && <Alert severity="error">Progress unavailable: {error}</Alert>}
    </Box>
  );
}
