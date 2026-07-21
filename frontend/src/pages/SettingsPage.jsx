import { useEffect, useState } from "react";
import {
  Box,
  Card,
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
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/Delete";
import { getSettings, saveSettings } from "../api";

// Must mirror the provider ids in backend/app/core/llm_providers.py PROVIDER_CONFIGS.
const PROVIDERS = [
  { id: "deepseek", label: "DeepSeek" },
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic" },
  { id: "gemini", label: "Gemini" },
  { id: "custom", label: "Custom / self-hosted" },
];

export default function SettingsPage({ user, onNavigate }) {
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

  async function loadSettings() {
    setLoading(true);
    setError("");
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
    if (user?.role === "admin") loadSettings();
    else setLoading(false);
  }, [user]);

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

  if (!(user.role === "admin")) {
    return (
      <Box component="section" sx={{ display: "flex", py: 4, textAlign: "center" }}>
        <Box sx={{ width: "100%", mt: 5 }}>
          <Typography sx={{ color: "text.secondary" }}>
            Access Denied. Administrator privileges required for settings.
          </Typography>
          <Button variant="contained" onClick={() => onNavigate("auth")} sx={{ mt: 2 }}>
            Go to Login
          </Button>
        </Box>
      </Box>
    );
  }

  return (
    <Box
      component="section"
      sx={{
        display: "flex",
        gap: 3,
        flexDirection: { xs: "column", md: "row" },
        pt: "54px",
        pb: "28px",
      }}
    >
      {/* Sidebar */}
      <Card
        sx={{
          width: { xs: "100%", md: 260 },
          flexShrink: 0,
          p: 3,
          alignSelf: "flex-start",
        }}
      >
        <Typography variant="subtitle2">Settings</Typography>
        <Typography variant="h2" sx={{ fontSize: 24, mb: 2 }}>Workspace setup</Typography>
        <Button
          fullWidth
          sx={{
            justifyContent: "flex-start",
            color: "#fff",
            backgroundColor: "#214f42",
            borderRadius: "8px",
            fontWeight: 750,
            textTransform: "none",
            mb: 2,
            "&:hover": { backgroundColor: "#1a3f35" },
          }}
        >
          LLM providers
        </Button>
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          Saved values are kept on the backend and override the local .env file. Each provider
          needs its own key configured before it appears as a model choice in Chat.
        </Typography>
      </Card>

      {/* Main content */}
      <Card sx={{ flex: 1, p: 3 }}>
        <Box sx={{ mb: "20px" }}>
          <Typography variant="subtitle2">Configuration</Typography>
          <Typography variant="h2" sx={{ fontSize: 24 }}>LLM providers</Typography>
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
              {PROVIDERS.map((provider) => (
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
          </>
        )}
      </Card>

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
    </Box>
  );
}
