import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  MenuItem,
  Skeleton,
  TextField,
  Typography,
} from "@mui/material";
import CloudDownloadOutlinedIcon from "@mui/icons-material/CloudDownloadOutlined";
import LanguageOutlinedIcon from "@mui/icons-material/LanguageOutlined";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";
import { getSettings, importWebDocument, saveSettings } from "../../api";

const ACCENT = "#214f42";
const PROVIDERS = [
  { id: "firecrawl", label: "Firecrawl", available: true },
  { id: "tavily", label: "Tavily", available: false },
];

function Field({ label, hint, children }) {
  return (
    <Box sx={{ display: "grid", gap: 0.5 }}>
      <Typography component="label" variant="body2" sx={{ fontWeight: 800 }}>
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

function SubCard({ icon, title, description, children }) {
  return (
    <Box
      sx={{
        p: 2,
        border: "1px solid #e2e5df",
        borderRadius: 2,
        display: "grid",
        gap: 2,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.25 }}>
        <Box sx={{ color: ACCENT, display: "flex", pt: 0.1 }}>{icon}</Box>
        <Box>
          <Typography variant="body2" sx={{ fontWeight: 800, color: ACCENT }}>
            {title}
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary", mt: 0.35 }}>
            {description}
          </Typography>
        </Box>
      </Box>
      {children}
    </Box>
  );
}

export default function WebSearchSection({
  user,
  onNavigate,
  onDocumentsChanged,
  configurationVersion = 0,
  onConfigurationChanged,
}) {
  const canEdit = user?.role === "admin";
  const [settings, setSettings] = useState(null);
  const [provider, setProvider] = useState("firecrawl");
  const [keyInput, setKeyInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [settingsNotice, setSettingsNotice] = useState("");
  const [settingsError, setSettingsError] = useState("");

  const [importUrl, setImportUrl] = useState("");
  const [importTitle, setImportTitle] = useState("");
  const [importBusy, setImportBusy] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importError, setImportError] = useState("");

  async function loadSettings() {
    setLoading(true);
    setSettingsError("");
    try {
      const result = await getSettings();
      setSettings(result);
      setProvider(result.web_search_provider || "firecrawl");
      setKeyInput("");
    } catch (loadError) {
      setSettingsError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSettings();
  }, [configurationVersion]);

  async function handleImport(event) {
    event.preventDefault();
    const url = importUrl.trim();
    setImportError("");
    setImportResult(null);

    try {
      const parsed = new URL(url);
      if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error();
    } catch {
      setImportError("Enter a complete public web address beginning with http:// or https://.");
      return;
    }

    setImportBusy(true);
    try {
      const result = await importWebDocument(url, importTitle);
      // The Library page queries its own live result set, while Chat renders
      // sources from App's shared document cache. Refresh that cache as part
      // of the import so a newly imported page added in Library is immediately
      // available when the user returns to Chat.
      await onDocumentsChanged?.([result.id]);
      setImportResult(result);
      setImportUrl("");
      setImportTitle("");
    } catch (error) {
      setImportError(error.message);
    } finally {
      setImportBusy(false);
    }
  }

  async function handleSave(event) {
    event.preventDefault();
    setSettingsBusy(true);
    setSettingsNotice("");
    setSettingsError("");
    try {
      const result = await saveSettings({
        web_search_provider: provider,
        ...(keyInput.trim()
          ? { web_search_provider_api_keys: { [provider]: keyInput.trim() } }
          : {}),
      });
      setSettings(result);
      setProvider(result.web_search_provider || "firecrawl");
      setKeyInput("");
      setSettingsNotice("Web search settings saved.");
      onConfigurationChanged?.();
    } catch (error) {
      setSettingsError(error.message);
    } finally {
      setSettingsBusy(false);
    }
  }

  async function handleClearKey() {
    if (!window.confirm("Remove the saved access key for this search service?")) return;
    setSettingsBusy(true);
    setSettingsNotice("");
    setSettingsError("");
    try {
      const result = await saveSettings({
        web_search_provider_api_keys: { [provider]: "" },
      });
      setSettings(result);
      setSettingsNotice("Saved access key removed.");
      onConfigurationChanged?.();
    } catch (error) {
      setSettingsError(error.message);
    } finally {
      setSettingsBusy(false);
    }
  }

  const activeProvider = PROVIDERS.find((item) => item.id === provider);
  const savedKey = settings?.masked_web_search_provider_keys?.[provider] || null;

  return (
    <>
      <Box sx={{ mb: "20px", display: "flex", alignItems: "center", gap: 1.5 }}>
        <Box>
          <Typography variant="subtitle2">Configuration</Typography>
          <Typography variant="h2" sx={{ fontSize: 24 }}>Web search</Typography>
        </Box>
        <Box sx={{ flex: 1 }} />
        <Chip
          label="Administrators only"
          size="small"
          sx={{ bgcolor: "#dfe8e0", color: ACCENT, fontWeight: 700 }}
        />
      </Box>

      <Typography variant="body2" sx={{ color: "text.secondary", mb: 2.5 }}>
        Add useful public pages to the shared library and choose the service Chat uses when it
        needs current information from the web.
      </Typography>

      <Box sx={{ display: "grid", gap: 2.5 }}>
        <SubCard
          icon={<CloudDownloadOutlinedIcon fontSize="small" />}
          title="Add a web page to the library"
          description="Paste a public page address. The page is checked for duplicates, converted into searchable content, and made available through the shared library."
        >
          <Box component="form" onSubmit={handleImport} sx={{ display: "grid", gap: 2 }}>
            <Field
              label="Page address"
              hint="Use the direct address of a public article, report, policy page, or guidance page."
            >
              <TextField
                value={importUrl}
                onChange={(event) => setImportUrl(event.target.value)}
                placeholder="https://example.org/policy-page"
                type="url"
                autoComplete="url"
                size="small"
                fullWidth
                required
                disabled={!canEdit || importBusy}
              />
            </Field>
            <Field
              label="Display title (optional)"
              hint="Leave blank to use the page title supplied by the website."
            >
              <TextField
                value={importTitle}
                onChange={(event) => setImportTitle(event.target.value)}
                placeholder="For example: Australian AI policy guidance"
                size="small"
                fullWidth
                inputProps={{ maxLength: 200 }}
                disabled={!canEdit || importBusy}
              />
            </Field>

            {importError && <Alert severity="error">{importError}</Alert>}
            {importResult && (
              <Alert
                severity="success"
                action={
                  <Button
                    color="inherit"
                    size="small"
                    endIcon={<OpenInNewOutlinedIcon fontSize="small" />}
                    onClick={() => onNavigate?.("library")}
                  >
                    Open library
                  </Button>
                }
              >
                {importResult.was_duplicate
                  ? `This page was already in the library as “${importResult.title}”.`
                  : `“${importResult.title}” was imported and is ready to search.`}
              </Alert>
            )}

            <Box>
              <Button
                type="submit"
                variant="contained"
                startIcon={<CloudDownloadOutlinedIcon />}
                disabled={!canEdit || importBusy || !importUrl.trim()}
              >
                {importBusy ? "Importing page..." : "Import page"}
              </Button>
            </Box>
          </Box>
        </SubCard>

        <Divider />

        <Box>
          <Typography variant="h3" sx={{ fontSize: 18, mb: 0.5 }}>Search service</Typography>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            This service retrieves public pages when Chat needs information that is not available
            in the document library.
          </Typography>
        </Box>

        {loading ? (
          <Box sx={{ py: 1 }}>
            <Skeleton variant="rounded" height={112} sx={{ mb: 2 }} />
            <Skeleton variant="rounded" height={128} />
          </Box>
        ) : (
          <Box component="form" onSubmit={handleSave} sx={{ display: "grid", gap: 2 }}>
            {settingsNotice && <Alert severity="success">{settingsNotice}</Alert>}
            {settingsError && <Alert severity="error">{settingsError}</Alert>}
            {!activeProvider?.available && (
              <Alert severity="warning">
                This search service is not available yet. Choose Firecrawl to use web search and
                page import.
              </Alert>
            )}

            <SubCard
              icon={<LanguageOutlinedIcon fontSize="small" />}
              title="Provider"
              description="Choose the service that retrieves and reads public web pages. Firecrawl is currently supported."
            >
              <Field label="Search provider">
                <TextField
                  select
                  value={provider}
                  onChange={(event) => {
                    setProvider(event.target.value);
                    setKeyInput("");
                  }}
                  size="small"
                  sx={{ maxWidth: 360 }}
                  disabled={!canEdit || settingsBusy}
                >
                  {PROVIDERS.map((item) => (
                    <MenuItem key={item.id} value={item.id} disabled={!item.available}>
                      {item.label}{item.available ? "" : " — coming soon"}
                    </MenuItem>
                  ))}
                </TextField>
              </Field>
            </SubCard>

            <SubCard
              icon={<LanguageOutlinedIcon fontSize="small" />}
              title="Access key"
              description="The provider uses this private key to authorise web searches and page imports. The saved value is never shown in full."
            >
              <Field
                label={`${activeProvider?.label || "Provider"} access key`}
                hint={
                  savedKey
                    ? `A key is saved (${savedKey}). Leave this field blank to keep it.`
                    : "No key is currently saved."
                }
              >
                <TextField
                  value={keyInput}
                  onChange={(event) => setKeyInput(event.target.value)}
                  placeholder={savedKey ? "Leave blank to keep the saved key" : "Enter access key"}
                  type="password"
                  autoComplete="new-password"
                  size="small"
                  fullWidth
                  disabled={!canEdit || settingsBusy}
                />
              </Field>

              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                <Button type="submit" variant="contained" disabled={!canEdit || settingsBusy}>
                  {settingsBusy ? "Saving..." : "Save settings"}
                </Button>
                <Button
                  type="button"
                  variant="outlined"
                  color="error"
                  disabled={!canEdit || settingsBusy || !savedKey}
                  onClick={handleClearKey}
                >
                  Remove saved key
                </Button>
                <Button type="button" variant="outlined" disabled={settingsBusy} onClick={loadSettings}>
                  Reload
                </Button>
              </Box>
            </SubCard>
          </Box>
        )}
      </Box>
    </>
  );
}
