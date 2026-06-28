import { useEffect, useState } from "react";
import {
  Box,
  Card,
  Typography,
  Button,
  TextField,
  Alert,
  CircularProgress,
  Skeleton,
} from "@mui/material";
import { getSettings, saveSettings } from "../api";

export default function SettingsPage({ user, onNavigate }) {
  const [settings, setSettings] = useState(null);
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
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
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (user) loadSettings();
    else setLoading(false);
  }, [user]);

  async function handleSave(event) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await saveSettings({
        llm_api_key: apiKey.trim() ? apiKey : null,
        llm_chat_model: model,
      });
      setSettings(result);
      setModel(result.llm_chat_model || "");
      setApiKey("");
      setNotice("Token settings saved.");
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleClearToken() {
    if (!window.confirm("Clear the saved token and fall back to .env if present?")) return;

    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await saveSettings({
        llm_api_key: "",
        llm_chat_model: model,
      });
      setSettings(result);
      setApiKey("");
      setNotice("Saved token cleared.");
    } catch (clearError) {
      setError(clearError.message);
    } finally {
      setBusy(false);
    }
  }

  if (!user) {
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
          API token
        </Button>
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          Saved values are kept on the backend and override the local .env file.
        </Typography>
      </Card>

      {/* Main content */}
      <Card sx={{ flex: 1, p: 3 }}>
        <Box sx={{ mb: "20px" }}>
          <Typography variant="subtitle2">Configuration</Typography>
          <Typography variant="h2" sx={{ fontSize: 24 }}>API token</Typography>
        </Box>

        {loading ? (
          <Box sx={{ py: 2 }}>
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", sm: "1fr 1fr 1fr 1fr" }, gap: 2, mb: 3 }}>
              {Array.from({ length: 4 }).map((_, i) => (
                <Box key={i}>
                  <Skeleton variant="text" width={60} height={16} />
                  <Skeleton variant="text" width="80%" height={28} />
                </Box>
              ))}
            </Box>
            <Skeleton variant="text" width="30%" height={20} sx={{ mb: 1 }} />
            <Skeleton variant="rounded" height={42} sx={{ mb: 2 }} />
            <Skeleton variant="text" width="30%" height={20} sx={{ mb: 1 }} />
            <Skeleton variant="rounded" height={42} sx={{ mb: 2 }} />
            <Box sx={{ display: "flex", gap: 1 }}>
              <Skeleton variant="rounded" width={120} height={40} />
              <Skeleton variant="rounded" width={80} height={40} />
              <Skeleton variant="rounded" width={140} height={40} />
            </Box>
          </Box>
        ) : (
          <>
            {/* Status grid */}
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr 1fr", sm: "1fr 1fr 1fr 1fr" },
                gap: 2,
                mb: 3,
              }}
            >
              <Box>
                <Typography variant="body2" sx={{ color: "#64716b", fontWeight: 800 }}>
                  Status
                </Typography>
                <Typography sx={{ fontWeight: 700, mt: 0.5 }}>
                  {settings?.llm_configured ? "Configured" : "Not configured"}
                </Typography>
              </Box>
              <Box>
                <Typography variant="body2" sx={{ color: "#64716b", fontWeight: 800 }}>
                  Token
                </Typography>
                <Typography sx={{ fontWeight: 700, mt: 0.5 }}>
                  {settings?.masked_llm_api_key || "None"}
                </Typography>
              </Box>
              <Box>
                <Typography variant="body2" sx={{ color: "#64716b", fontWeight: 800 }}>
                  Source
                </Typography>
                <Typography sx={{ fontWeight: 700, mt: 0.5 }}>
                  {settings?.llm_api_key_source || "missing"}
                </Typography>
              </Box>
              <Box>
                <Typography variant="body2" sx={{ color: "#64716b", fontWeight: 800 }}>
                  Model source
                </Typography>
                <Typography sx={{ fontWeight: 700, mt: 0.5 }}>
                  {settings?.llm_chat_model_source || "default"}
                </Typography>
              </Box>
            </Box>

            {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

            <Box component="form" onSubmit={handleSave} sx={{ display: "grid", gap: 2 }}>
              <Box sx={{ display: "grid", gap: 0.5 }}>
                <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                  New API key
                </Typography>
                <TextField
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="Leave blank to keep the current token"
                  type="password"
                  autoComplete="off"
                  size="small"
                  fullWidth
                />
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  Leave this empty to keep the token currently in use.
                </Typography>
              </Box>
              <Box sx={{ display: "grid", gap: 0.5 }}>
                <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                  Chat model
                </Typography>
                <TextField
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  placeholder="Enter the chat model name"
                  size="small"
                  fullWidth
                />
              </Box>
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                <Button variant="contained" disabled={busy} type="submit">
                  {busy ? "Saving..." : "Save settings"}
                </Button>
                <Button variant="outlined" disabled={busy} onClick={loadSettings}>
                  Reload
                </Button>
                <Button
                  variant="outlined"
                  color="error"
                  disabled={busy}
                  onClick={handleClearToken}
                >
                  Clear saved token
                </Button>
              </Box>
            </Box>
          </>
        )}
      </Card>
    </Box>
  );
}
