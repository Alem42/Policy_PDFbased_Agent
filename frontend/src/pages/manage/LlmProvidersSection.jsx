import { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Button,
  TextField,
  MenuItem,
  Alert,
  Skeleton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Collapse,
  Divider,
  Chip,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/Delete";
import { getSettings, saveSettings, getModelCatalog, addCatalogEntry } from "../../api";

const CAPABILITIES = [
  "chat",
  "chat_async",
  "embedding",
  "rerank",
  "image",
  "image_async",
  "video",
  "audio",
  "voice",
  "tokenizer",
  "ocr",
  "async_result",
];
const EMPTY_ENDPOINT = {
  provider: "",
  provider_label: "",
  capability: "embedding",
  model: "",
  base_url: "",
  endpoint: "",
  dimensions: "",
};

// Must mirror the provider ids in backend/app/core/llm_providers.py PROVIDER_CONFIGS.
const PROVIDERS = [
  { id: "deepseek", label: "DeepSeek" },
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic" },
  { id: "gemini", label: "Gemini" },
  { id: "custom", label: "Custom / self-hosted" },
];

// LLM provider + API key configuration (renders inside the Manage content card).
export default function LlmProvidersSection() {
  const [settings, setSettings] = useState(null);
  const [llmProvider, setLlmProvider] = useState("deepseek");
  const [model, setModel] = useState("");
  const [providerKeyInputs, setProviderKeyInputs] = useState({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  // "Manage models" dialog — edits the curated model list for one provider at a time.
  const [modelDialogOpen, setModelDialogOpen] = useState(false);
  const [modelDialogProvider, setModelDialogProvider] = useState("deepseek");
  const [modelDialogRows, setModelDialogRows] = useState([]);
  const [modelDialogBusy, setModelDialogBusy] = useState(false);
  const [modelDialogError, setModelDialogError] = useState("");

  // Model catalog (known provider/model endpoints, no keys).
  const [catalog, setCatalog] = useState([]);
  const [showCatalog, setShowCatalog] = useState(false);
  const [endpointForm, setEndpointForm] = useState(EMPTY_ENDPOINT);
  const [catalogBusy, setCatalogBusy] = useState(false);
  const [catalogError, setCatalogError] = useState("");
  const [catalogProviderFilter, setCatalogProviderFilter] = useState("all");
  const [catalogCapabilityFilter, setCatalogCapabilityFilter] = useState("all");

  async function loadSettings() {
    setLoading(true);
    setError("");
    getModelCatalog()
      .then((r) => setCatalog(r.entries || []))
      .catch(() => setCatalog([]));
    try {
      const result = await getSettings();
      setSettings(result);
      setModel(result.llm_chat_model || "");
      setLlmProvider(result.llm_provider || "deepseek");
      setProviderKeyInputs({});
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSettings();
  }, []);

  // Key list = chat providers + any distinct catalog providers (one key per company).
  const keyProviders = [...PROVIDERS];
  const known = new Set(PROVIDERS.map((p) => p.id));
  for (const entry of catalog) {
    if (!known.has(entry.provider)) {
      known.add(entry.provider);
      keyProviders.push({ id: entry.provider, label: entry.provider_label });
    }
  }
  const catalogProviders = Array.from(
    new Map(
      catalog.map((entry) => [
        entry.provider,
        { id: entry.provider, label: entry.provider_label },
      ]),
    ).values(),
  ).sort((a, b) => a.label.localeCompare(b.label));
  const catalogCapabilities = [...new Set(catalog.map((entry) => entry.capability))].sort();
  const filteredCatalog = catalog.filter(
    (entry) =>
      (catalogProviderFilter === "all" || entry.provider === catalogProviderFilter) &&
      (catalogCapabilityFilter === "all" ||
        entry.capability === catalogCapabilityFilter),
  );

  async function handleAddEndpoint() {
    setCatalogBusy(true);
    setCatalogError("");
    try {
      await addCatalogEntry({
        ...endpointForm,
        provider: endpointForm.provider.trim(),
        model: endpointForm.model.trim(),
        base_url: endpointForm.base_url.trim(),
        dimensions: endpointForm.dimensions === "" ? null : Number(endpointForm.dimensions),
      });
      const r = await getModelCatalog();
      setCatalog(r.entries || []);
      setEndpointForm(EMPTY_ENDPOINT);
    } catch (addError) {
      setCatalogError(addError.message);
    } finally {
      setCatalogBusy(false);
    }
  }

  async function handleSave(event) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    setError("");
    try {
      // Only send keys the admin actually typed — omitted providers keep their saved key.
      const providerApiKeys = Object.fromEntries(
        Object.entries(providerKeyInputs).filter(([, value]) => value.trim()),
      );
      const result = await saveSettings({
        llm_chat_model: model,
        llm_provider: llmProvider,
        ...(Object.keys(providerApiKeys).length > 0 ? { provider_api_keys: providerApiKeys } : {}),
      });
      setSettings(result);
      setModel(result.llm_chat_model || "");
      setLlmProvider(result.llm_provider || "deepseek");
      setProviderKeyInputs({});
      setNotice("Settings saved.");
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleClearProviderKey(providerId) {
    if (!window.confirm(`Clear the saved key for ${providerId} and fall back to .env if present?`)) return;

    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await saveSettings({ provider_api_keys: { [providerId]: "" } });
      setSettings(result);
      setNotice(`Cleared the saved key for ${providerId}.`);
    } catch (clearError) {
      setError(clearError.message);
    } finally {
      setBusy(false);
    }
  }

  function openModelDialog(providerId) {
    const initialProvider = providerId || llmProvider;
    setModelDialogProvider(initialProvider);
    setModelDialogRows((settings?.provider_models?.[initialProvider] || []).map((m) => ({ ...m })));
    setModelDialogError("");
    setModelDialogOpen(true);
  }

  function switchModelDialogProvider(providerId) {
    setModelDialogProvider(providerId);
    setModelDialogRows((settings?.provider_models?.[providerId] || []).map((m) => ({ ...m })));
  }

  function updateModelRow(index, field, value) {
    setModelDialogRows((rows) => rows.map((r, i) => (i === index ? { ...r, [field]: value } : r)));
  }

  function addModelRow() {
    setModelDialogRows((rows) => [...rows, { id: "", label: "" }]);
  }

  function removeModelRow(index) {
    setModelDialogRows((rows) => rows.filter((_, i) => i !== index));
  }

  function resetModelDialogToDefault() {
    setModelDialogRows(
      (settings?.default_provider_models?.[modelDialogProvider] || []).map((m) => ({ ...m })),
    );
  }

  async function handleSaveModelDialog() {
    setModelDialogBusy(true);
    setModelDialogError("");
    try {
      const cleanRows = modelDialogRows
        .map((r) => ({ id: r.id.trim(), label: r.label.trim() || r.id.trim() }))
        .filter((r) => r.id);
      const result = await saveSettings({ provider_models: { [modelDialogProvider]: cleanRows } });
      setSettings(result);
      setModelDialogOpen(false);
      setNotice(`Updated the model list for ${modelDialogProvider}.`);
    } catch (saveError) {
      setModelDialogError(saveError.message);
    } finally {
      setModelDialogBusy(false);
    }
  }

  return (
    <>
      <Box sx={{ mb: "20px" }}>
        <Typography variant="subtitle2">Configuration</Typography>
        <Typography variant="h2" sx={{ fontSize: 24 }}>LLM &amp; API keys</Typography>
      </Box>

      {loading ? (
        <Box sx={{ py: 2 }}>
          <Skeleton variant="text" width="30%" height={20} sx={{ mb: 1 }} />
          <Skeleton variant="rounded" height={42} sx={{ mb: 2 }} />
          <Skeleton variant="text" width="30%" height={20} sx={{ mb: 1 }} />
          <Skeleton variant="rounded" height={42} sx={{ mb: 2 }} />
          <Skeleton variant="rounded" height={42} sx={{ mb: 2 }} />
          <Skeleton variant="rounded" height={42} sx={{ mb: 2 }} />
        </Box>
      ) : (
        <>
          <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
            Default provider status:{" "}
            <strong>{settings?.llm_configured ? "Configured" : "Not configured"}</strong>
            {" "}({settings?.llm_api_key_source || "missing"}), model{" "}
            <strong>{settings?.llm_chat_model}</strong> ({settings?.llm_chat_model_source})
          </Typography>

          {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <Box component="form" onSubmit={handleSave} sx={{ display: "grid", gap: 2 }}>
            <Box sx={{ display: "grid", gap: 0.5 }}>
              <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                Default provider
              </Typography>
              <TextField
                select
                value={llmProvider}
                onChange={(event) => {
                  const nextProvider = event.target.value;
                  setLlmProvider(nextProvider);
                  // Drop a model choice that doesn't exist for the newly selected provider.
                  const validIds = (settings?.provider_models?.[nextProvider] || []).map((m) => m.id);
                  if (nextProvider !== "custom" && !validIds.includes(model)) {
                    setModel("");
                  }
                }}
                size="small"
                sx={{ maxWidth: 320 }}
              >
                {PROVIDERS.map((provider) => (
                  <MenuItem key={provider.id} value={provider.id}>
                    {provider.label}
                  </MenuItem>
                ))}
              </TextField>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                Used for chat messages that don't explicitly pick a model.
              </Typography>
            </Box>

            <Box sx={{ display: "grid", gap: 0.5 }}>
              <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                Default chat model override
              </Typography>
              {llmProvider === "custom" ? (
                <TextField
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  placeholder="Enter the self-hosted model name"
                  size="small"
                  sx={{ maxWidth: 320 }}
                />
              ) : (
                <TextField
                  select
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  size="small"
                  sx={{ maxWidth: 320 }}
                >
                  <MenuItem value="">
                    <em>Use provider's built-in default</em>
                  </MenuItem>
                  {/* Keep a saved value visible even if it predates this curated list. */}
                  {model && !(settings?.provider_models?.[llmProvider] || []).some((m) => m.id === model) && (
                    <MenuItem value={model}>{model}</MenuItem>
                  )}
                  {(settings?.provider_models?.[llmProvider] || []).map((option) => (
                    <MenuItem key={option.id} value={option.id}>
                      {option.label}
                    </MenuItem>
                  ))}
                </TextField>
              )}
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                Only applies to the default provider above.
              </Typography>
            </Box>

            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mt: 1 }}>
              <Typography variant="body2" sx={{ fontWeight: 800 }}>
                Provider API keys
              </Typography>
              <Button size="small" variant="outlined" onClick={() => openModelDialog()}>
                Manage models
              </Button>
            </Box>
            {keyProviders.map((provider) => (
              <Box
                key={provider.id}
                sx={{
                  display: "grid",
                  gridTemplateColumns: { xs: "1fr", sm: "140px 1fr auto" },
                  gap: 1,
                  alignItems: "center",
                  p: 1.5,
                  border: "1px solid #e2e5df",
                  borderRadius: 2,
                }}
              >
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>{provider.label}</Typography>
                  <Typography variant="caption" sx={{ color: "text.secondary" }}>
                    {settings?.masked_provider_keys?.[provider.id] || "Not configured"}
                  </Typography>
                </Box>
                <TextField
                  value={providerKeyInputs[provider.id] || ""}
                  onChange={(event) =>
                    setProviderKeyInputs((current) => ({
                      ...current,
                      [provider.id]: event.target.value,
                    }))
                  }
                  placeholder="Leave blank to keep the current key"
                  type="password"
                  autoComplete="off"
                  size="small"
                  fullWidth
                />
                <Button
                  size="small"
                  color="error"
                  variant="outlined"
                  disabled={busy || !settings?.masked_provider_keys?.[provider.id]}
                  onClick={() => handleClearProviderKey(provider.id)}
                >
                  Clear
                </Button>
              </Box>
            ))}

            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mt: 1 }}>
              <Button variant="contained" disabled={busy} type="submit">
                {busy ? "Saving..." : "Save settings"}
              </Button>
              <Button variant="outlined" disabled={busy} onClick={loadSettings}>
                Reload
              </Button>
            </Box>
          </Box>

          {/* Model catalog: known provider/model endpoints (no keys) */}
          <Divider sx={{ my: 3 }} />
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            <Typography variant="body2" sx={{ fontWeight: 800 }}>
              API endpoints ({catalog.length})
            </Typography>
            <Typography variant="caption" sx={{ color: "text.secondary", flex: 1, minWidth: 120 }}>
              Provider/model reference used by the Embedding &amp; Reranker pages. Keys are entered above.
            </Typography>
            <Button size="small" variant="outlined" onClick={() => setShowCatalog((v) => !v)}>
              {showCatalog ? "Hide endpoints" : "Show all endpoints"}
            </Button>
            {/* TODO(crawler): auto-populate the catalog by scanning provider docs.
                Wire to a backend crawler / web-search job later; POST /admin/catalog. */}
            <Button size="small" variant="text" disabled title="Coming soon">
              Rescan (crawler)
            </Button>
          </Box>

          <Collapse in={showCatalog}>
            <Box sx={{ mt: 2, display: "grid", gap: 1 }}>
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1,
                  flexWrap: "wrap",
                  mb: 0.5,
                }}
              >
                <TextField
                  select
                  label="Company"
                  value={catalogProviderFilter}
                  onChange={(event) => setCatalogProviderFilter(event.target.value)}
                  size="small"
                  sx={{ minWidth: 180 }}
                >
                  <MenuItem value="all">All companies</MenuItem>
                  {catalogProviders.map((provider) => (
                    <MenuItem key={provider.id} value={provider.id}>
                      {provider.label}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  select
                  label="Function"
                  value={catalogCapabilityFilter}
                  onChange={(event) => setCatalogCapabilityFilter(event.target.value)}
                  size="small"
                  sx={{ minWidth: 180 }}
                >
                  <MenuItem value="all">All functions</MenuItem>
                  {catalogCapabilities.map((capability) => (
                    <MenuItem key={capability} value={capability}>
                      {capability}
                    </MenuItem>
                  ))}
                </TextField>
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  Showing {filteredCatalog.length} of {catalog.length}
                </Typography>
              </Box>

              {filteredCatalog.map((entry, index) => (
                <Box
                  key={`${entry.provider}-${entry.capability}-${entry.model}-${index}`}
                  sx={{
                    display: "grid",
                    gridTemplateColumns: { xs: "1fr", sm: "160px 96px 1fr" },
                    gap: 1,
                    alignItems: "center",
                    p: 1,
                    border: "1px solid #eef0ec",
                    borderRadius: 1.5,
                  }}
                >
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>{entry.provider_label}</Typography>
                  <Chip label={entry.capability} size="small" sx={{ height: 20, fontSize: 11, justifySelf: "start" }} />
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {entry.model}{entry.dimensions ? ` · ${entry.dimensions}d` : ""}
                    </Typography>
                    <Typography variant="caption" sx={{ color: "text.secondary", display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {entry.base_url}{entry.endpoint}
                    </Typography>
                  </Box>
                </Box>
              ))}
              {filteredCatalog.length === 0 && (
                <Typography
                  variant="body2"
                  sx={{ color: "text.secondary", py: 2, textAlign: "center" }}
                >
                  No endpoints match these filters.
                </Typography>
              )}

              {/* Add an endpoint manually (crawler will do this in bulk later) */}
              <Box sx={{ mt: 1, p: 1.5, border: "1px solid #e2e5df", borderRadius: 2, display: "grid", gap: 1 }}>
                <Typography variant="body2" sx={{ fontWeight: 800 }}>Add an endpoint</Typography>
                {catalogError && <Alert severity="error">{catalogError}</Alert>}
                <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 1 }}>
                  <TextField
                    label="Provider id" value={endpointForm.provider} size="small" placeholder="zhipu"
                    onChange={(e) => setEndpointForm((f) => ({ ...f, provider: e.target.value, provider_label: f.provider_label || e.target.value }))}
                  />
                  <TextField
                    select label="Capability" value={endpointForm.capability} size="small"
                    onChange={(e) => setEndpointForm((f) => ({ ...f, capability: e.target.value }))}
                  >
                    {CAPABILITIES.map((cap) => (<MenuItem key={cap} value={cap}>{cap}</MenuItem>))}
                  </TextField>
                  <TextField
                    label="Model" value={endpointForm.model} size="small" placeholder="embedding-3"
                    onChange={(e) => setEndpointForm((f) => ({ ...f, model: e.target.value }))}
                  />
                  <TextField
                    label="Dimensions (optional)" value={endpointForm.dimensions} type="number" size="small"
                    onChange={(e) => setEndpointForm((f) => ({ ...f, dimensions: e.target.value }))}
                  />
                  <TextField
                    label="Base URL" value={endpointForm.base_url} size="small" fullWidth placeholder="https://…/v1"
                    onChange={(e) => setEndpointForm((f) => ({ ...f, base_url: e.target.value }))}
                  />
                  <TextField
                    label="Endpoint path" value={endpointForm.endpoint} size="small" fullWidth placeholder="/embeddings"
                    onChange={(e) => setEndpointForm((f) => ({ ...f, endpoint: e.target.value }))}
                  />
                </Box>
                <Button
                  variant="outlined" size="small" startIcon={<AddIcon />} onClick={handleAddEndpoint}
                  disabled={catalogBusy || !endpointForm.provider.trim() || !endpointForm.model.trim()}
                  sx={{ justifySelf: "start" }}
                >
                  {catalogBusy ? "Adding..." : "Add endpoint"}
                </Button>
              </Box>
            </Box>
          </Collapse>
        </>
      )}

      {/* Manage models dialog */}
      <Dialog open={modelDialogOpen} onClose={() => setModelDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Manage models</DialogTitle>
        <DialogContent sx={{ display: "grid", gap: 2 }}>
          <TextField
            select
            label="Provider"
            value={modelDialogProvider}
            onChange={(event) => switchModelDialogProvider(event.target.value)}
            size="small"
            sx={{ maxWidth: 280, mt: 1 }}
          >
            {PROVIDERS.map((provider) => (
              <MenuItem key={provider.id} value={provider.id}>
                {provider.label}
              </MenuItem>
            ))}
          </TextField>

          {modelDialogError && <Alert severity="error">{modelDialogError}</Alert>}

          <Box sx={{ display: "grid", gap: 1 }}>
            {modelDialogRows.length === 0 && (
              <Typography variant="body2" sx={{ color: "text.secondary" }}>
                No models configured for this provider yet.
              </Typography>
            )}
            {modelDialogRows.map((row, index) => (
              <Box key={index} sx={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 1 }}>
                <TextField
                  value={row.id}
                  onChange={(event) => updateModelRow(index, "id", event.target.value)}
                  placeholder="Model id (e.g. gpt-4o)"
                  size="small"
                />
                <TextField
                  value={row.label}
                  onChange={(event) => updateModelRow(index, "label", event.target.value)}
                  placeholder="Display label (e.g. GPT-4o)"
                  size="small"
                />
                <IconButton size="small" onClick={() => removeModelRow(index)} sx={{ color: "#888" }}>
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Box>
            ))}
            <Button size="small" variant="text" startIcon={<AddIcon />} onClick={addModelRow} sx={{ justifySelf: "start" }}>
              Add model
            </Button>
          </Box>
        </DialogContent>
        <DialogActions sx={{ justifyContent: "space-between", px: 3, pb: 2 }}>
          <Button size="small" onClick={resetModelDialogToDefault} disabled={modelDialogBusy}>
            Reset to default
          </Button>
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button onClick={() => setModelDialogOpen(false)} disabled={modelDialogBusy}>
              Cancel
            </Button>
            <Button variant="contained" onClick={handleSaveModelDialog} disabled={modelDialogBusy}>
              {modelDialogBusy ? "Saving..." : "Save"}
            </Button>
          </Box>
        </DialogActions>
      </Dialog>
    </>
  );
}
