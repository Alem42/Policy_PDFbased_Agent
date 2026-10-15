import { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Chip, Typography } from "@mui/material";
import { getDocumentTasks, retryDocumentTask } from "../api";

export default function DocumentTasks() {
  const [data, setData] = useState({ items: [], counts: {} });
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(null);
  const refresh = useCallback(async () => {
    try {
      setData(await getDocumentTasks());
      setError("");
    } catch (cause) { setError(cause.message); }
  }, []);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [refresh]);

  async function retry(id) {
    setRetrying(id);
    try { await retryDocumentTask(id); await refresh(); }
    catch (cause) { setError(cause.message); }
    finally { setRetrying(null); }
  }

  return (
    <Box sx={{ my: 3, p: 2, border: "1px solid #dce5df", borderRadius: 2 }}>
      <Typography variant="h6">Document processing tasks</Typography>
      <Typography variant="body2" sx={{ color: "text.secondary", mb: 1 }}>
        Processing continues after a server restart. Failed tasks can be retried.
      </Typography>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mb: 2 }}>
        {["queued", "running", "succeeded", "failed"].map((status) => (
          <Chip key={status} label={`${status}: ${data.counts[status] || 0}`} size="small" />
        ))}
        <Button size="small" onClick={refresh}>Refresh tasks</Button>
      </Box>
      {error && <Alert severity="error">{error}</Alert>}
      {!data.items.length && <Typography variant="body2">No processing tasks yet.</Typography>}
      {data.items.slice(0, 15).map((task) => (
        <Box key={task.id} sx={{ py: 1, borderTop: "1px solid #e8ede9" }}>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>{task.original_filename}</Typography>
            <Chip size="small" label={task.status}
              color={task.status === "failed" ? "error" : task.status === "succeeded" ? "success" : "default"} />
            <Typography variant="caption">Attempts: {task.attempts}/{task.max_attempts}</Typography>
            {task.status === "failed" && <Button size="small" disabled={retrying === task.id}
              onClick={() => retry(task.id)}>Retry task</Button>}
          </Box>
          {task.last_error && <Typography variant="caption" color="error">{task.last_error}</Typography>}
        </Box>
      ))}
    </Box>
  );
}
