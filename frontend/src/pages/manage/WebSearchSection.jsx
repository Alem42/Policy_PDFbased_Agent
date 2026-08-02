import { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Button,
  TextField,
  MenuItem,
  Alert,
  Skeleton,
  Chip,
} from "@mui/material";
import { getSettings, saveSettings } from "../../api";

// Keep in sync with backend KNOWN_WEB_SEARCH_PROVIDERS
// (app/modules/settings/service.py). Tavily has a real provider class
// (chat/rag/web_search/providers/tavily.py) but it's a stub -- selecting it
// or calling search_web/import_web_page raises "not implemented yet" at
// request time, not from this form.
const KNOWN_PROVIDERS = [
  { id: "firecrawl", label: "Firecrawl", implemented: true },
  { id: "tavily", label: "Tavily", implemented: false },
];

// Web search provider + API key configuration (renders inside the Manage
// content card). Powers the agent's search_web and import_web_page tools.
export default function WebSearchSection({ configurationVersion = 0, onConfigurationChanged }) {
  const [settings, setSettings] = useState(null);
  const [provider, setProvider] = useState("firecrawl");
  const [keyInputs, setKeyInputs] = useState({});
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
      setProvider(result.web_search_provider || "firecrawl");
      setKeyInputs({});
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSettings();
  }, [configurationVersion]);

  async function handleSave(event) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const webSearchProviderApiKeys = Object.fromEntries(
        Object.entries(keyInputs).filter(([, value]) => value.trim()),
      );
      const result = await saveSettings({
        web_search_provider: provider,
        ...(Object.keys(webSearchProviderApiKeys).length > 0
          ? { web_search_provider_api_keys: webSearchProviderApiKeys }
          : {}),
      });
      setSettings(result);
      setProvider(result.web_search_provider || "firecrawl");
      setKeyInputs({});
      setNotice("Settings saved.");
      onConfigurationChanged?.();
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleClearKey(providerId) {
    if (!window.confirm(`Clear the saved key for ${providerId}?`)) return;
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await saveSettings({ web_search_provider_api_keys: { [providerId]: "" } });
      setSettings(result);
      setNotice(`Cleared the saved key for ${providerId}.`);
      onConfigurationChanged?.();
    } catch (clearError) {
      setError(clearError.message);
    } finally {
      setBusy(false);
    }
  }

  const activeProvider = KNOWN_PROVIDERS.find((p) => p.id === provider);

  return (
    <>
      <Box sx={{ mb: "20px" }}>
        <Typography variant="subtitle2">Configuration</Typography>
        <Typography variant="h2" sx={{ fontSize: 24 }}>Web search</Typography>
      </Box>

      {loading ? (
        <Box sx={{ py: 2 }}>
          <Skeleton variant="text" width="30%" height={20} sx={{ mb: 1 }} />
          <Skeleton variant="rounded" height={42} sx={{ mb: 2 }} />
          <Skeleton variant="rounded" height={72} sx={{ mb: 2 }} />
        </Box>
      ) : (
        <>
          <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
            Powers the chat agent's <code>search_web</code> and <code>import_web_page</code> tools
            (Manage &gt; document access still controls who sees imported pages).
          </Typography>

          {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          {!activeProvider?.implemented && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              Tavily is not implemented yet — selecting it will make search_web/import_web_page
              fail at request time. Firecrawl is the only working provider right now.
            </Alert>
          )}

          <Box component="form" onSubmit={handleSave} sx={{ display: "grid", gap: 2 }}>
            <Box sx={{ display: "grid", gap: 0.5 }}>
              <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                Active provider
              </Typography>
              <TextField
                select
                value={provider}
                onChange={(event) => setProvider(event.target.value)}
                size="small"
                sx={{ maxWidth: 320 }}
              >
                {KNOWN_PROVIDERS.map((p) => (
                  <MenuItem key={p.id} value={p.id}>
                    {p.label}
                    {!p.implemented ? " (not implemented)" : ""}
                  </MenuItem>
                ))}
              </TextField>
            </Box>

            <Typography variant="body2" sx={{ fontWeight: 800, mt: 1 }}>
              API keys
            </Typography>
            {KNOWN_PROVIDERS.map((p) => (
              <Box
                key={p.id}
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
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>{p.label}</Typography>
                  {p.id === provider && (
                    <Chip
                      label="Active"
                      size="small"
                      sx={{ height: 18, fontSize: 10, fontWeight: 700, bgcolor: "#dfe8e0", color: "#214f42" }}
                    />
                  )}
                </Box>
                <Box>
                  <TextField
                    value={keyInputs[p.id] || ""}
                    onChange={(event) =>
                      setKeyInputs((current) => ({ ...current, [p.id]: event.target.value }))
                    }
                    placeholder="Leave blank to keep the current key"
                    type="password"
                    autoComplete="off"
                    size="small"
                    fullWidth
                  />
                  <Typography variant="caption" sx={{ color: "text.secondary" }}>
                    {settings?.masked_web_search_provider_keys?.[p.id]
                      ? `Current: ${settings.masked_web_search_provider_keys[p.id]}`
                      : p.id === "firecrawl"
                        ? "Not configured — falls back to the FIRECRAWL_API_KEY env var if set."
                        : "Not configured"}
                  </Typography>
                </Box>
                <Button
                  size="small"
                  color="error"
                  variant="outlined"
                  disabled={busy || !settings?.masked_web_search_provider_keys?.[p.id]}
                  onClick={() => handleClearKey(p.id)}
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
    </>
  );
}
