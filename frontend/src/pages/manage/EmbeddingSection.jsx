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
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from "@mui/material";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import {
  getEmbeddingSettings,
  saveEmbeddingSettings,
  testEmbeddingConnection,
  reembedLibrary,
  rescanDocuments,
  getSettings,
} from "../../api";
import CatalogModelPicker from "./CatalogModelPicker";

const ACCENT = "#214f42";

// Debug-phase defaults. Kept broad on purpose so the whole pipeline is tunable
// from the UI while the backend is being wired; trim later once stable.
const DEFAULTS = {
  provider: "local", // "local" | "api"
  local_model: "BAAI/bge-small-en-v1.5",
  api_provider: "", // catalog provider id (e.g. "zhipu")
  api_base_url: "",
  api_key: "",
  api_model: "",
  dimensions: 1024,
  auto_detect_dimensions: true,
  symmetric: true,
  batch_size: 32,
  chunk_token_budget: 480,
  token_counting: "auto", // "auto" | "model" | "tiktoken"
  distance_metric: "cosine", // "cosine" | "l2" | "ip"
  evidence_distance_threshold: 0.45,
};

// Curated local models fastembed can download by name (weights + tokenizer + dim
// come with the model). "custom" lets an admin type any fastembed-supported id.
const LOCAL_MODELS = [
  { id: "BAAI/bge-small-en-v1.5", label: "bge-small-en-v1.5 · 384d · English" },
  { id: "BAAI/bge-base-en-v1.5", label: "bge-base-en-v1.5 · 768d · English" },
  { id: "intfloat/multilingual-e5-large", label: "multilingual-e5-large · 1024d · multilingual" },
  { id: "custom", label: "Custom (enter fastembed model id)…" },
];

const TOKEN_MODES = [
  { id: "auto", label: "Auto (model tokenizer if local, else tiktoken)" },
  { id: "model", label: "Model tokenizer (exact, local only)" },
  { id: "tiktoken", label: "tiktoken approx (cl100k_base)" },
];

const DISTANCE_METRICS = [
  { id: "cosine", label: "Cosine (default)" },
  { id: "l2", label: "Euclidean (L2)" },
  { id: "ip", label: "Inner product" },
];

// Small labelled field wrapper matching the LLM section's layout.
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

// Embedding model configuration (renders inside the Manage content card).
export default function EmbeddingSection({
  onNavigate,
  configurationVersion = 0,
  onConfigurationChanged,
}) {
  const [form, setForm] = useState(DEFAULTS);
  const [status, setStatus] = useState(null); // backend-reported active state, if any
  const [connected, setConnected] = useState(false); // whether the backend endpoint exists yet
  const [customLocal, setCustomLocal] = useState(false);
  const [providersWithKey, setProvidersWithKey] = useState(null); // Set of provider ids with a key
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [initial, setInitial] = useState(DEFAULTS); // last-loaded/saved settings, to diff against

  function set(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  // Apply a catalog provider+model pick (keys stay on the LLM & API keys page).
  function handlePick({ provider, model, base_url, dimensions }) {
    setForm((prev) => ({
      ...prev,
      api_provider: provider,
      api_model: model,
      api_base_url: base_url !== undefined ? base_url : prev.api_base_url,
      dimensions: dimensions ?? prev.dimensions,
    }));
  }

  async function load() {
    setLoading(true);
    setError("");
    // Which providers already have a key (from the central LLM & API keys store).
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
      const result = await getEmbeddingSettings();
      const loaded = { ...DEFAULTS, ...(result.settings || result) };
      setForm(loaded);
      setInitial(loaded);
      setStatus(result.status || null);
      setConnected(true);
      const model = (result.settings || result).local_model;
      setCustomLocal(!!model && !LOCAL_MODELS.some((m) => m.id === model));
    } catch {
      // Backend endpoint not implemented yet — run in local draft mode.
      setConnected(false);
      setForm(DEFAULTS);
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [configurationVersion]);

  const targetModel = form.provider === "local" ? form.local_model : form.api_model;

  // Diff the form against the last-saved settings, one entry per changed field.
  // severity "warning" = heavy (needs re-embed or full rescan); "info" = immediate.
  function computeChanges() {
    const c = [];
    const modelChanged =
      form.provider !== initial.provider ||
      (form.provider === "local"
        ? form.local_model !== initial.local_model
        : form.api_provider !== initial.api_provider || form.api_model !== initial.api_model);

    if (modelChanged) {
      c.push({
        key: "model",
        severity: "warning",
        label: "Active embedding model",
        message:
          `Switches to “${targetModel}”. Its vectors live in a separate table — if this model ` +
          "has no vectors yet, run “Re-embed library” to populate it. Other models' vectors are " +
          "kept, so switching to an already-embedded model is instant (no re-scan).",
      });
    } else if (form.dimensions !== initial.dimensions) {
      c.push({
        key: "dim",
        severity: "warning",
        label: "Vector dimension",
        message: "A different dimension uses a different vector table — run Re-embed library.",
      });
    }
    if (form.chunk_token_budget !== initial.chunk_token_budget) {
      c.push({
        key: "chunk",
        severity: "warning",
        label: "Chunk token budget",
        message:
          "Changes how documents are split. Applies to NEW documents only — run “Rescan all " +
          "documents” to re-chunk existing ones (heavy: re-extract + re-chunk + re-embed). Keep it " +
          "within the model's input limit (bge ≈512, embedding-3 ≤3072).",
      });
    }
    if (form.token_counting !== initial.token_counting) {
      c.push({
        key: "tok",
        severity: "info",
        label: "Token counting",
        message: "How chunk size is measured. Affects newly processed documents only.",
      });
    }
    if (form.batch_size !== initial.batch_size) {
      c.push({
        key: "batch",
        severity: "info",
        label: "Batch size",
        message: "Texts per embedding call. Affects ingestion speed only; no re-embed needed.",
      });
    }
    if (form.evidence_distance_threshold !== initial.evidence_distance_threshold) {
      c.push({
        key: "evid",
        severity: "info",
        label: "Evidence distance threshold",
        message: "Takes effect immediately for new questions. No re-embedding needed.",
      });
    }
    return c;
  }

  const pendingChanges = computeChanges();

  // Show the review dialog whenever there are changes; save directly if none.
  function requestSave(event) {
    event.preventDefault();
    if (pendingChanges.length > 0) setSaveDialogOpen(true);
    else doSave();
  }

  async function doSave() {
    setSaveDialogOpen(false);
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await saveEmbeddingSettings(form);
      const saved = { ...DEFAULTS, ...(result.settings || result) };
      setForm(saved);
      setInitial(saved);
      setStatus(result.status || null);
      setConnected(true);
      setNotice("Embedding settings saved. Re-embed the library for the change to take effect.");
      onConfigurationChanged?.();
      // Tell the header (and any listener) to refresh the active-model display.
      window.dispatchEvent(new Event("embedding-config-changed"));
    } catch (saveError) {
      // Keep the form as-is so nothing typed is lost while the backend is pending.
      setError(
        connected
          ? saveError.message
          : "Backend endpoint /admin/embedding is not implemented yet — settings not persisted.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleRescanAll() {
    if (
      !window.confirm(
        "Rescan ALL documents? This fully reprocesses every document (re-extract, re-chunk, " +
          "re-generate metadata, and re-embed the active model) and may take a while.",
      )
    ) {
      return;
    }
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await rescanDocuments();
      setNotice(`Rescan started: ${result.reprocessed ?? 0} document(s) reprocessed.`);
    } catch (rescanError) {
      setError(rescanError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setNotice("");
    setError("");
    try {
      const result = await testEmbeddingConnection(form);
      setNotice(
        `Connection OK — model "${result.model || form.api_model}" returned ${result.dimension ?? "?"}-dim ` +
          `vectors in ${result.latency_ms ?? "?"} ms.`,
      );
    } catch (testError) {
      setError(
        connected ? testError.message : "Backend test endpoint not implemented yet.",
      );
    } finally {
      setTesting(false);
    }
  }

  async function handleReembed() {
    if (
      !window.confirm(
        "Re-embed the library into the active model's vector table? Reuses existing chunks " +
          "(no re-extract) and keeps other models' vectors. Needed after switching to a model " +
          "that has no vectors yet.",
      )
    ) {
      return;
    }
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await reembedLibrary();
      setNotice(
        `Re-embedded ${result.chunks ?? 0} chunk(s) across ${result.documents ?? 0} document(s) ` +
          `into "${result.model ?? "active model"}".`,
      );
    } catch (reembedError) {
      setError(reembedError.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <Box sx={{ py: 2 }}>
        <Skeleton variant="text" width="30%" height={20} sx={{ mb: 1 }} />
        <Skeleton variant="rounded" height={120} sx={{ mb: 2 }} />
        <Skeleton variant="rounded" height={160} sx={{ mb: 2 }} />
        <Skeleton variant="rounded" height={120} />
      </Box>
    );
  }

  const isApi = form.provider === "api";

  return (
    <>
      <Box sx={{ mb: "20px", display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="subtitle2">Configuration</Typography>
          <Typography variant="h2" sx={{ fontSize: 24 }}>Embedding model</Typography>
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

      {!connected && (
        <Alert severity="info" sx={{ mb: 2 }}>
          The <code>/admin/embedding</code> endpoints are not implemented yet. This form is fully
          usable for tuning; values are held locally and will persist once the backend is wired.
        </Alert>
      )}
      {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {status && (
        <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
          Active: <strong>{status.provider}</strong> · model <strong>{status.model}</strong> ·{" "}
          <strong>{status.dimension}</strong>-dim · vector table{" "}
          <strong>{status.vector_table || "—"}</strong>
        </Typography>
      )}

      <Box component="form" onSubmit={requestSave} sx={{ display: "grid", gap: 2 }}>
        {/* Provider mode */}
        <SubCard title="Provider">
          <Field
            label="Embedding mode"
            hint="Local runs on-box via fastembed (no network). API calls an OpenAI-compatible endpoint (e.g. Zhipu)."
          >
            <TextField
              select
              value={form.provider}
              onChange={(e) => set("provider", e.target.value)}
              size="small"
              sx={{ maxWidth: 320 }}
            >
              <MenuItem value="local">Local (fastembed)</MenuItem>
              <MenuItem value="api">API (OpenAI-compatible)</MenuItem>
            </TextField>
          </Field>
        </SubCard>

        {/* Local model */}
        {!isApi && (
          <SubCard title="Local model">
            <Field
              label="Model"
              hint="These are selectable options, not installed models — only the active one is downloaded (on first use), with its tokenizer and dimension."
            >
              <TextField
                select
                value={customLocal ? "custom" : form.local_model}
                onChange={(e) => {
                  if (e.target.value === "custom") {
                    setCustomLocal(true);
                  } else {
                    setCustomLocal(false);
                    set("local_model", e.target.value);
                  }
                }}
                size="small"
                sx={{ maxWidth: 420 }}
              >
                {LOCAL_MODELS.map((m) => (
                  <MenuItem key={m.id} value={m.id}>{m.label}</MenuItem>
                ))}
              </TextField>
            </Field>
            {customLocal && (
              <Field label="Custom model id" hint="Any fastembed-supported HuggingFace id, e.g. BAAI/bge-small-en-v1.5">
                <TextField
                  value={form.local_model}
                  onChange={(e) => set("local_model", e.target.value)}
                  placeholder="org/model-name"
                  size="small"
                  sx={{ maxWidth: 420 }}
                />
              </Field>
            )}
          </SubCard>
        )}

        {/* API model — pick a catalogued provider + model. Keys live on the LLM & API keys page. */}
        {isApi && (
          <SubCard title="API model">
            <CatalogModelPicker
              capability="embedding"
              provider={form.api_provider}
              model={form.api_model}
              providersWithKey={providersWithKey}
              onNavigate={onNavigate}
              onPick={({ api_key, ...pick }) => {
                handlePick(pick);
                if (api_key !== undefined) set("api_key", api_key);
              }}
              manualBaseUrl={form.api_base_url}
              manualApiKey={form.api_key}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={form.auto_detect_dimensions}
                  onChange={(e) => set("auto_detect_dimensions", e.target.checked)}
                />
              }
              label="Auto-detect dimension on save (probe once, read vector length)"
            />
            <Field label="Dimensions" hint="From the catalog; auto-detected on save unless you override. A change requires a re-embed.">
              <TextField
                value={form.dimensions}
                onChange={(e) => set("dimensions", Number(e.target.value))}
                type="number"
                size="small"
                disabled={form.auto_detect_dimensions}
                sx={{ maxWidth: 200 }}
              />
            </Field>
          </SubCard>
        )}

        {/* Chunking & tokens */}
        <SubCard title="Chunking & tokens">
          <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
            <Field label="Batch size" hint="Texts per embedding call.">
              <TextField
                value={form.batch_size}
                onChange={(e) => set("batch_size", Number(e.target.value))}
                type="number"
                size="small"
                sx={{ width: 160 }}
              />
            </Field>
            <Field label="Chunk token budget" hint="Max tokens per chunk. Keep below the model's input limit.">
              <TextField
                value={form.chunk_token_budget}
                onChange={(e) => set("chunk_token_budget", Number(e.target.value))}
                type="number"
                size="small"
                sx={{ width: 200 }}
              />
            </Field>
          </Box>
          <Field label="Token counting" hint="Local models have an exact tokenizer; API models fall back to a tiktoken approximation.">
            <TextField
              select
              value={form.token_counting}
              onChange={(e) => set("token_counting", e.target.value)}
              size="small"
              sx={{ maxWidth: 420 }}
            >
              {TOKEN_MODES.map((m) => (
                <MenuItem key={m.id} value={m.id}>{m.label}</MenuItem>
              ))}
            </TextField>
          </Field>
        </SubCard>

        {/* Retrieval & evidence (debug knobs) */}
        <SubCard title="Retrieval & evidence (debug)">
          <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
            <Field
              label="Distance metric"
              hint="Cosine only. Changing it would require rebuilding each vector index and re-calibrating the evidence threshold, so it is fixed for now."
            >
              <TextField
                select
                value="cosine"
                size="small"
                disabled
                sx={{ width: 220 }}
              >
                {DISTANCE_METRICS.map((m) => (
                  <MenuItem key={m.id} value={m.id}>{m.label}</MenuItem>
                ))}
              </TextField>
            </Field>
            <Field label="Evidence distance threshold" hint="Chunks above this distance are treated as non-evidence. Re-calibrate per model.">
              <TextField
                value={form.evidence_distance_threshold}
                onChange={(e) => set("evidence_distance_threshold", Number(e.target.value))}
                type="number"
                inputProps={{ step: 0.01 }}
                size="small"
                sx={{ width: 220 }}
              />
            </Field>
          </Box>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            The reranker (cross-encoder) is configured separately in Manage → Reranker.
          </Typography>
        </SubCard>

        <Divider sx={{ my: 1 }} />

        {/* Actions */}
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
          <Button variant="contained" disabled={busy} type="submit">
            {busy ? "Saving..." : "Save embedding settings"}
          </Button>
          {isApi && (
            <Button variant="outlined" disabled={testing} onClick={handleTest}>
              {testing ? "Testing..." : "Test connection"}
            </Button>
          )}
          <Box sx={{ flex: 1 }} />
          <Button variant="outlined" disabled={busy} onClick={load}>
            Reload
          </Button>
          <Button variant="outlined" color="warning" disabled={busy} onClick={handleReembed}>
            Re-embed library
          </Button>
          <Button variant="outlined" color="warning" disabled={busy} onClick={handleRescanAll}>
            Rescan all documents
          </Button>
        </Box>
      </Box>

      {/* Review changes before saving — one line per changed setting. */}
      <Dialog open={saveDialogOpen} onClose={() => setSaveDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Review changes</DialogTitle>
        <DialogContent>
          {pendingChanges.some((c) => c.severity === "warning") && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              Some changes need a re-embed or full re-scan to take effect on existing documents.
            </Alert>
          )}
          <Box sx={{ display: "grid", gap: 1.5 }}>
            {pendingChanges.map((change) => (
              <Box key={change.key} sx={{ display: "flex", gap: 1.25, alignItems: "flex-start" }}>
                {change.severity === "warning" ? (
                  <WarningAmberOutlinedIcon sx={{ fontSize: 20, color: "#b5820a", mt: 0.25 }} />
                ) : (
                  <InfoOutlinedIcon sx={{ fontSize: 20, color: "#64716b", mt: 0.25 }} />
                )}
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 800 }}>
                    {change.label}
                  </Typography>
                  <Typography variant="body2" sx={{ color: "#4b564f" }}>
                    {change.message}
                  </Typography>
                </Box>
              </Box>
            ))}
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setSaveDialogOpen(false)} disabled={busy}>
            Cancel
          </Button>
          <Button variant="contained" onClick={doSave} disabled={busy}>
            {busy ? "Saving..." : "Save changes"}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
