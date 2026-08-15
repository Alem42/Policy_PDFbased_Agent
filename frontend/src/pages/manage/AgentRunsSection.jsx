import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Paper,
  Typography,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import { getAgentRun, getAgentRuns } from "../../api";

function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function milliseconds(value) {
  return Number.isFinite(value) ? `${value.toFixed(1)} ms` : "—";
}

function EventRow({ event }) {
  const tokens = event.token_usage?.total_tokens;
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "36px 1fr", md: "36px 210px 1fr 100px 90px" },
        gap: 1,
        alignItems: "center",
        py: 0.9,
        borderBottom: "1px solid #edf0ec",
      }}
    >
      <Typography variant="caption" sx={{ color: "text.secondary" }}>#{event.sequence}</Typography>
      <Typography variant="body2" sx={{ fontWeight: 700 }}>{event.event_type}</Typography>
      <Typography variant="caption" sx={{ color: "text.secondary" }}>
        {event.tool_name || event.node_name || "run"}
      </Typography>
      <Typography variant="caption">{milliseconds(event.duration_ms)}</Typography>
      <Typography variant="caption">{Number.isInteger(tokens) ? `${tokens} tok` : ""}</Typography>
    </Box>
  );
}

export default function AgentRunsSection() {
  const [runs, setRuns] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setRuns(await getAgentRuns(50));
    } catch (err) {
      setError(err.message || "Could not load agent runs.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  async function openRun(runId) {
    setDetailLoading(true);
    setError("");
    try {
      setSelected(await getAgentRun(runId));
    } catch (err) {
      setError(err.message || "Could not load this run.");
    } finally {
      setDetailLoading(false);
    }
  }

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 800 }}>Agent run traces</Typography>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            Inspect sanitized latency, Tool order, token usage and run outcomes.
          </Typography>
        </Box>
        <Button startIcon={<RefreshIcon />} onClick={loadRuns} disabled={loading}>Refresh</Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {loading ? (
        <Box sx={{ py: 5, textAlign: "center" }}><CircularProgress size={28} /></Box>
      ) : runs.length === 0 ? (
        <Alert severity="info">No run events yet. Start a new streamed chat to create one.</Alert>
      ) : (
        <Box sx={{ display: "grid", gap: 1 }}>
          {runs.map((run) => (
            <Paper
              key={run.run_id}
              variant="outlined"
              onClick={() => openRun(run.run_id)}
              sx={{ p: 1.5, cursor: "pointer", "&:hover": { borderColor: "#214f42" } }}
            >
              <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
                <Typography variant="body2" sx={{ fontWeight: 800, fontFamily: "monospace" }}>
                  {run.run_id}
                </Typography>
                <Chip size="small" label={`${run.event_count || 0} events`} />
                <Chip size="small" variant="outlined" label={run.profile?.workflow_mode || "unknown"} />
              </Box>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                {run.model || "default model"} · {formatDate(run.started_at)}
              </Typography>
            </Paper>
          ))}
        </Box>
      )}

      {(detailLoading || selected) && <Divider sx={{ my: 3 }} />}
      {detailLoading ? (
        <CircularProgress size={24} />
      ) : selected ? (
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 800, mb: 0.5 }}>Selected trace</Typography>
          <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary" }}>
            {selected.run.run_id}
          </Typography>
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", my: 1.5 }}>
            <Chip size="small" label={selected.run.profile?.source_policy || "unknown source policy"} />
            <Chip size="small" label={selected.run.prompt_version} variant="outlined" />
            <Chip size="small" label={selected.run.configuration_version} variant="outlined" />
          </Box>
          <Paper variant="outlined" sx={{ px: 1.5 }}>
            {selected.events.map((event) => <EventRow key={event.sequence} event={event} />)}
          </Paper>
        </Box>
      ) : null}
    </Box>
  );
}
