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
} from "@mui/material";
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
                  onChange={(event) => setLlmProvider(event.target.value)}
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
                <TextField
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  placeholder="Leave blank to use the default provider's built-in model"
                  size="small"
                  sx={{ maxWidth: 320 }}
                />
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  Only applies to the default provider above.
                </Typography>
              </Box>

              <Typography variant="body2" sx={{ fontWeight: 800, mt: 1 }}>
                Provider API keys
              </Typography>
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
    </Box>
  );
}
