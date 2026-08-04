import { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Button,
  TextField,
  Alert,
  Skeleton,
  Switch,
  FormControlLabel,
  Chip,
} from "@mui/material";
import { getSuggestionSettings, saveSuggestionSettings } from "../../api";

const ACCENT = "#214f42";
const DEFAULTS = { enabled: true, max_suggestions: 3 };

function Field({ label, hint, children }) {
  return (
    <Box sx={{ display: "grid", gap: 0.5 }}>
      <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
        {label}
      </Typography>
      {children}
      {hint && (
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          {hint}
        </Typography>
      )}
    </Box>
  );
}

function SubCard({ title, children }) {
  return (
    <Box sx={{ p: 2, border: "1px solid #e2e5df", borderRadius: 2, display: "grid", gap: 2 }}>
      <Typography variant="body2" sx={{ fontWeight: 800, color: ACCENT }}>
        {title}
      </Typography>
      {children}
    </Box>
  );
}

// Follow-up suggestion configuration (renders inside the Manage content card).
export default function SuggestionsSection({ configurationVersion = 0, onConfigurationChanged }) {
  const [form, setForm] = useState(DEFAULTS);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  function set(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function load() {
    setLoading(true);
    setError("");
    try {
      const result = await getSuggestionSettings();
      setForm({ ...DEFAULTS, ...(result.settings || result) });
      setConnected(true);
    } catch {
      setConnected(false);
      setForm(DEFAULTS);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [configurationVersion]);

  async function handleSave(event) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await saveSuggestionSettings({
        enabled: form.enabled,
        max_suggestions: Number(form.max_suggestions),
      });
      setForm({ ...DEFAULTS, ...(result.settings || result) });
      setConnected(true);
      setNotice("Suggestion settings saved. They apply to new answers immediately.");
      onConfigurationChanged?.();
    } catch (saveError) {
      setError(
        connected
          ? saveError.message
          : "The suggestions settings service is unavailable, so changes were not saved.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <Box sx={{ py: 2 }}>
        <Skeleton variant="text" width="30%" height={20} sx={{ mb: 1 }} />
        <Skeleton variant="rounded" height={120} sx={{ mb: 2 }} />
        <Skeleton variant="rounded" height={140} />
      </Box>
    );
  }

  return (
    <>
      <Box sx={{ mb: "20px", display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="subtitle2">Configuration</Typography>
          <Typography variant="h2" sx={{ fontSize: 24 }}>Suggested follow-ups</Typography>
        </Box>
        <Box sx={{ flex: 1 }} />
        {!connected && (
          <Chip
            label="Backend not reachable"
            size="small"
            sx={{ backgroundColor: "#fbeee0", color: "#8a5a1a", fontWeight: 700 }}
          />
        )}
      </Box>

      <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
        Show useful next questions below a document-grounded answer. Each suggestion is checked
        against the same documents and evidence rules as a normal chat question before users see it.
      </Typography>

      {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Box component="form" onSubmit={handleSave} sx={{ display: "grid", gap: 2 }}>
        <FormControlLabel
          control={<Switch checked={form.enabled} onChange={(e) => set("enabled", e.target.checked)} />}
          label="Enable follow-up suggestions"
        />

        <SubCard title="Display">
          <Field
            label="Suggestions shown"
            hint="Recommended: 3. Choose between 1 and 8 questions below each answer."
          >
            <TextField
              value={form.max_suggestions}
              onChange={(e) => set("max_suggestions", e.target.value)}
              type="number"
              inputProps={{ min: 1, max: 8 }}
              size="small"
              sx={{ width: 160 }}
            />
          </Field>
        </SubCard>

        <Alert severity="info">
          Quality controls are automatic: the system creates two spare candidates, reuses the
          active Embedding Evidence Gate and Reranker, checks five chunks per candidate, and keeps
          questions under 140 characters.
        </Alert>

        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
          <Button variant="contained" disabled={busy} type="submit">
            {busy ? "Saving..." : "Save suggestion settings"}
          </Button>
          <Box sx={{ flex: 1 }} />
          <Button variant="outlined" disabled={busy} onClick={load}>
            Reload
          </Button>
        </Box>
      </Box>
    </>
  );
}
