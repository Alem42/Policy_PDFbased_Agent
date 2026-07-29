import { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Button,
  TextField,
  MenuItem,
  Alert,
  Skeleton,
  Switch,
  FormControlLabel,
  Chip,
} from "@mui/material";
import {
  getRerankingSettings,
  saveRerankingSettings,
  testRerankingConnection,
  getSettings,
} from "../../api";
import CatalogModelPicker from "./CatalogModelPicker";

const ACCENT = "#214f42";

const DEFAULTS = {
  enabled: true,
  provider: "local", // "local" | "api"
  local_model: "BAAI/bge-reranker-base",
  api_provider: "", // catalog provider id
  api_base_url: "",
  api_key: "",
  api_model: "rerank",
  min_score: "", // "" -> provider default (local -7.0, api 0.2)
};

// Field + SubCard mirror the Embedding section's layout.
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

// Reranker (cross-encoder) configuration (renders inside the Manage content card).
export default function RerankingSection({ onNavigate }) {
  const [form, setForm] = useState(DEFAULTS);
  const [status, setStatus] = useState(null);
  const [connected, setConnected] = useState(false);
  const [providersWithKey, setProvidersWithKey] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  function set(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function load() {
    setLoading(true);
    setError("");
    getSettings()
      .then((s) =>
        setProvidersWithKey(
          new Set(
            Object.entries(s.masked_provider_keys || {})
              .filter(([, masked]) => Boolean(masked))
              .map(([provider]) => provider),
          ),
        ),
      )
      .catch(() => setProvidersWithKey(null));
    try {
      const result = await getRerankingSettings();
      const s = result.settings || result;
      setForm({ ...DEFAULTS, ...s, min_score: s.min_score ?? "" });
      setStatus(result.status || null);
      setConnected(true);
    } catch {
      setConnected(false);
      setForm(DEFAULTS);
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function payload() {
    // Empty min_score -> null (use the provider default on the backend).
    const trimmed = String(form.min_score).trim();
    return { ...form, min_score: trimmed === "" ? null : Number(trimmed) };
  }

  async function handleSave(event) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await saveRerankingSettings(payload());
      const s = result.settings || result;
      setForm({ ...DEFAULTS, ...s, min_score: s.min_score ?? "" });
      setStatus(result.status || null);
      setConnected(true);
      setNotice("Reranker settings saved. Takes effect immediately for new questions.");
    } catch (saveError) {
      setError(
        connected
          ? saveError.message
          : "Backend endpoint /admin/reranking is not implemented yet — settings not persisted.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setNotice("");
    setError("");
    try {
      const result = await testRerankingConnection(payload());
      const scores = (result.sample_scores || []).join(", ");
      setNotice(
        `Connection OK — "${result.model}" scored the relevant/irrelevant sample as [${scores}]` +
          (result.latency_ms != null ? ` in ${result.latency_ms} ms.` : "."),
      );
    } catch (testError) {
      setError(connected ? testError.message : "Backend test endpoint not implemented yet.");
    } finally {
      setTesting(false);
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

  const isApi = form.provider === "api";

  return (
    <>
      <Box sx={{ mb: "20px", display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="subtitle2">Configuration</Typography>
          <Typography variant="h2" sx={{ fontSize: 24 }}>Reranker</Typography>
        </Box>
        <Box sx={{ flex: 1 }} />
        {!connected && (
          <Chip
            label="Draft — backend not wired yet"
            size="small"
            sx={{ backgroundColor: "#fbeee0", color: "#8a5a1a", fontWeight: 700 }}
          />
        )}
      </Box>

      <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
        The reranker is a cross-encoder that re-scores retrieved chunks against the question — a
        separate model from the embedding model. It improves ordering and feeds the evidence gate.
      </Typography>

      {!connected && (
        <Alert severity="info" sx={{ mb: 2 }}>
          The <code>/admin/reranking</code> endpoints are not implemented yet. This form is usable for
          tuning; values persist once the backend is wired.
        </Alert>
      )}
      {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {status && (
        <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
          Active: <strong>{status.enabled ? "on" : "off"}</strong> · <strong>{status.provider}</strong>{" "}
          · model <strong>{status.model}</strong> · evidence floor <strong>{status.min_score}</strong>
          {status.reuses_embedding_key ? " · reusing the embedding API key" : ""}
        </Typography>
      )}

      <Box component="form" onSubmit={handleSave} sx={{ display: "grid", gap: 2 }}>
        <FormControlLabel
          control={<Switch checked={form.enabled} onChange={(e) => set("enabled", e.target.checked)} />}
          label="Enable reranking (off = use dense vector ranking only)"
        />

        <SubCard title="Provider">
          <Field
            label="Reranker mode"
            hint="Local runs bge-reranker on-box (no network). API calls a Cohere-style /rerank endpoint (e.g. Zhipu)."
          >
            <TextField
              select
              value={form.provider}
              onChange={(e) => set("provider", e.target.value)}
              size="small"
              sx={{ maxWidth: 320 }}
            >
              <MenuItem value="local">Local (fastembed cross-encoder)</MenuItem>
              <MenuItem value="api">API (Cohere-style /rerank)</MenuItem>
            </TextField>
          </Field>

          {!isApi && (
            <Field label="Local model" hint="Downloaded on first use. e.g. BAAI/bge-reranker-base.">
              <TextField
                value={form.local_model}
                onChange={(e) => set("local_model", e.target.value)}
                size="small"
                sx={{ maxWidth: 420 }}
              />
            </Field>
          )}

          {isApi && (
            <CatalogModelPicker
              capability="rerank"
              provider={form.api_provider}
              model={form.api_model}
              providersWithKey={providersWithKey}
              onNavigate={onNavigate}
              onPick={({ provider, model, base_url, api_key }) =>
                setForm((prev) => ({
                  ...prev,
                  api_provider: provider,
                  api_model: model,
                  ...(base_url !== undefined ? { api_base_url: base_url } : {}),
                  ...(api_key !== undefined ? { api_key } : {}),
                }))
              }
              manualBaseUrl={form.api_base_url}
              manualApiKey={form.api_key}
            />
          )}
        </SubCard>

        <SubCard title="Evidence gate">
          <Field
            label="Reranker evidence floor (min score)"
            hint="Best reranker score below this = 'no relevant passage'. Blank = provider default (local -7.0, API 0.2). Scales differ per provider — recalibrate on your corpus (API scores can cluster near 1.0)."
          >
            <TextField
              value={form.min_score}
              onChange={(e) => set("min_score", e.target.value)}
              type="number"
              inputProps={{ step: 0.1 }}
              placeholder="provider default"
              size="small"
              sx={{ width: 220 }}
            />
          </Field>
        </SubCard>

        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
          <Button variant="contained" disabled={busy} type="submit">
            {busy ? "Saving..." : "Save reranker settings"}
          </Button>
          <Button variant="outlined" disabled={testing} onClick={handleTest}>
            {testing ? "Testing..." : "Test connection"}
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
