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

const DEFAULTS = {
  enabled: true,
  max_suggestions: 3,
  candidate_pool: 5,
  validation_distance: "", // "" -> null -> reuse the evidence gate's distance cutoff
  use_reranker_validation: true,
  validation_top_k: 5,
  temperature: 0.3,
  max_question_chars: 140,
  personalize: false,
};

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
      const s = result.settings || result;
      setForm({
        ...DEFAULTS,
        ...s,
        validation_distance: s.validation_distance ?? "",
      });
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

  function payload() {
    const distance = String(form.validation_distance).trim();
    return {
      ...form,
      max_suggestions: Number(form.max_suggestions),
      candidate_pool: Number(form.candidate_pool),
      validation_top_k: Number(form.validation_top_k),
      temperature: Number(form.temperature),
      max_question_chars: Number(form.max_question_chars),
      validation_distance: distance === "" ? null : Number(distance),
    };
  }

  async function handleSave(event) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await saveSuggestionSettings(payload());
      const s = result.settings || result;
      setForm({ ...DEFAULTS, ...s, validation_distance: s.validation_distance ?? "" });
      setConnected(true);
      setNotice("Suggestion settings saved. Takes effect immediately for new answers.");
      onConfigurationChanged?.();
    } catch (saveError) {
      setError(
        connected
          ? saveError.message
          : "Backend endpoint /admin/suggestions is not reachable — settings not persisted.",
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
        After each grounded answer, the system proposes a few next questions. Every candidate is
        re-checked against the selected documents with the same evidence gate a real question faces,
        so suggestions never point users at questions the documents can't answer.
      </Typography>

      {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Box component="form" onSubmit={handleSave} sx={{ display: "grid", gap: 2 }}>
        <FormControlLabel
          control={<Switch checked={form.enabled} onChange={(e) => set("enabled", e.target.checked)} />}
          label="Enable follow-up suggestions"
        />

        <SubCard title="Amount">
          <Field label="Suggestions shown" hint="How many chips to display under each answer (1–8).">
            <TextField
              value={form.max_suggestions}
              onChange={(e) => set("max_suggestions", e.target.value)}
              type="number"
              inputProps={{ min: 1, max: 8 }}
              size="small"
              sx={{ width: 160 }}
            />
          </Field>
          <Field
            label="Candidate pool"
            hint="How many candidates the model proposes before validation filters them. Larger = more choice but more retrieval work. Should be ≥ suggestions shown."
          >
            <TextField
              value={form.candidate_pool}
              onChange={(e) => set("candidate_pool", e.target.value)}
              type="number"
              inputProps={{ min: 1, max: 16 }}
              size="small"
              sx={{ width: 160 }}
            />
          </Field>
        </SubCard>

        <SubCard title="Quality gate">
          <Field
            label="Validation distance override"
            hint="Cosine-distance cutoff a candidate must beat to be shown. Blank = reuse the embedding evidence threshold. Set LOWER than the gate for stricter, higher-quality suggestions."
          >
            <TextField
              value={form.validation_distance}
              onChange={(e) => set("validation_distance", e.target.value)}
              type="number"
              inputProps={{ step: 0.01, min: 0, max: 2 }}
              placeholder="evidence gate default"
              size="small"
              sx={{ width: 220 }}
            />
          </Field>
          <FormControlLabel
            control={
              <Switch
                checked={form.use_reranker_validation}
                onChange={(e) => set("use_reranker_validation", e.target.checked)}
              />
            }
            label="Also apply the reranker evidence floor to candidates (when the reranker is on)"
          />
          <Field
            label="Chunks retrieved per candidate"
            hint="How many chunks to pull when validating each candidate (1–20). Small is cheap and enough."
          >
            <TextField
              value={form.validation_top_k}
              onChange={(e) => set("validation_top_k", e.target.value)}
              type="number"
              inputProps={{ min: 1, max: 20 }}
              size="small"
              sx={{ width: 160 }}
            />
          </Field>
        </SubCard>

        <SubCard title="Generation">
          <Field
            label="Creativity (temperature)"
            hint="Controls how varied the proposed follow-up questions are, not how much evidence supports them. 0–0.2 is focused and repeatable; 0.3–0.5 explores more wording and topic angles; higher values are more experimental and may create more candidates that the evidence checks reject. Recommended: 0.3."
          >
            <TextField
              value={form.temperature}
              onChange={(e) => set("temperature", e.target.value)}
              type="number"
              inputProps={{ step: 0.1, min: 0, max: 1.5 }}
              size="small"
              sx={{ width: 160 }}
            />
          </Field>
          <Field label="Max question length (characters)" hint="Keeps suggestions short and clickable (20–400).">
            <TextField
              value={form.max_question_chars}
              onChange={(e) => set("max_question_chars", e.target.value)}
              type="number"
              inputProps={{ min: 20, max: 400 }}
              size="small"
              sx={{ width: 160 }}
            />
          </Field>
          <FormControlLabel
            control={<Switch checked={form.personalize} onChange={(e) => set("personalize", e.target.checked)} />}
            label="Personalize from each user's past suggestion clicks (experimental)"
          />
        </SubCard>

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
