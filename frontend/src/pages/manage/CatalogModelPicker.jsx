import { useEffect, useState } from "react";
import { Box, Typography, TextField, MenuItem, Alert, Link } from "@mui/material";
import { getModelCatalog } from "../../api";

// Pick a provider -> model from the model catalog, filtered to one capability
// (embedding / rerank). Keys are NOT entered here — they live on the LLM & API
// keys page; this only switches which catalogued model is used.
export default function CatalogModelPicker({
  capability,
  provider,
  model,
  providersWithKey,
  onPick,
  onNavigate,
  manualBaseUrl = "",
  manualApiKey = "",
}) {
  const [entries, setEntries] = useState([]);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let active = true;
    getModelCatalog(capability)
      .then((r) => active && setEntries(r.entries || []))
      .catch(() => active && setLoadError(true));
    return () => {
      active = false;
    };
  }, [capability]);

  const providers = [];
  const seen = new Set();
  for (const e of entries) {
    if (!seen.has(e.provider)) {
      seen.add(e.provider);
      providers.push({ id: e.provider, label: e.provider_label });
    }
  }
  const models = entries.filter((e) => e.provider === provider);
  const isManual = provider === "__manual__";
  const hasKey = isManual
    ? Boolean(manualApiKey)
    : !providersWithKey || (provider && providersWithKey.has(provider));

  function selectProvider(p) {
    if (p === "__manual__") {
      onPick({
        provider: p,
        model: "",
        base_url: "",
        api_key: "",
        dimensions: null,
      });
      return;
    }
    const first = entries.find((e) => e.provider === p);
    onPick({
      provider: p,
      model: first?.model || "",
      base_url: first?.base_url || "",
      dimensions: first?.dimensions ?? null,
    });
  }

  function selectModel(m) {
    const e = entries.find((x) => x.provider === provider && x.model === m);
    onPick({
      provider,
      model: m,
      base_url: e?.base_url || "",
      dimensions: e?.dimensions ?? null,
    });
  }

  return (
    <Box sx={{ display: "grid", gap: 2 }}>
      {loadError && (
        <Alert severity="info">Catalog unavailable — the backend may not be wired yet.</Alert>
      )}

      <Box sx={{ display: "grid", gap: 0.5 }}>
        <Typography variant="body2" sx={{ fontWeight: 800 }}>Provider</Typography>
        <TextField
          select
          value={provider || ""}
          onChange={(e) => selectProvider(e.target.value)}
          size="small"
          sx={{ maxWidth: 340 }}
        >
          <MenuItem value=""><em>Select a provider…</em></MenuItem>
          {providers.map((p) => (
            <MenuItem key={p.id} value={p.id}>
              {p.label}
              {providersWithKey && !providersWithKey.has(p.id) ? " — no key" : ""}
            </MenuItem>
          ))}
          <MenuItem value="__manual__">Manual / unlisted provider</MenuItem>
        </TextField>
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          Choose a known source first. If it is not listed, choose Manual and enter the API details.
        </Typography>
      </Box>

      {isManual ? (
        <Box sx={{ display: "grid", gap: 1.5 }}>
          <TextField
            label="API base URL"
            value={manualBaseUrl}
            onChange={(e) =>
              onPick({ provider, model, base_url: e.target.value, api_key: manualApiKey })
            }
            placeholder={
              capability === "embedding"
                ? "https://provider.example/v1"
                : "https://provider.example/v1"
            }
            size="small"
            fullWidth
          />
          <TextField
            label="API key"
            value={manualApiKey}
            onChange={(e) =>
              onPick({ provider, model, base_url: manualBaseUrl, api_key: e.target.value })
            }
            type="password"
            autoComplete="off"
            placeholder="Paste API key (leave blank to keep the saved key)"
            size="small"
            fullWidth
          />
          <TextField
            label="Model name"
            value={model || ""}
            onChange={(e) =>
              onPick({
                provider,
                model: e.target.value,
                base_url: manualBaseUrl,
                api_key: manualApiKey,
              })
            }
            placeholder={capability === "embedding" ? "embedding-model-name" : "rerank-model-name"}
            size="small"
            sx={{ maxWidth: 460 }}
          />
        </Box>
      ) : (
        <Box sx={{ display: "grid", gap: 0.5 }}>
          <Typography variant="body2" sx={{ fontWeight: 800 }}>Model</Typography>
          <TextField
            select
            value={model || ""}
            onChange={(e) => selectModel(e.target.value)}
            size="small"
            sx={{ maxWidth: 460 }}
            disabled={!provider}
          >
            <MenuItem value=""><em>Select a model…</em></MenuItem>
            {models.map((e) => (
              <MenuItem key={e.model} value={e.model}>
                {e.model}
                {e.dimensions ? ` · ${e.dimensions}d` : ""}
                {e.notes ? ` · ${e.notes}` : ""}
              </MenuItem>
            ))}
          </TextField>
        </Box>
      )}

      {provider && !isManual && !hasKey && (
        <Alert severity="warning">
          No API key for “{provider}”. Add one on the{" "}
          <Link component="button" type="button" onClick={() => onNavigate?.("llm")}>
            LLM &amp; API keys
          </Link>{" "}
          page.
        </Alert>
      )}
    </Box>
  );
}
