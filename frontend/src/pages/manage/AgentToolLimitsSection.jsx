import { useEffect, useState } from "react";
import { Box, Typography, Button, TextField, Alert, Skeleton, Chip } from "@mui/material";
import { getAgentToolLimits, saveAgentToolLimits } from "../../api";

const ACCENT = "#214f42";

const DEFAULTS = {
  search_internal_documents: 5,
  search_full_corpus: 5,
  ask_user: 20,
  search_web: 4,
  import_web_page: 1,
  prepare_final_answer: 1,
};

const FIELDS = [
  {
    key: "search_internal_documents",
    label: "Search selected documents",
    hint: "How many times per turn the agent may search the user's selected documents (1–50).",
  },
  {
    key: "search_full_corpus",
    label: "Search full corpus",
    hint: "How many times per turn the agent may escalate to searching the entire library (1–50).",
  },
  {
    key: "ask_user",
    label: "Ask the user",
    hint: "How many clarifying questions per turn the agent may ask the user (1–50).",
  },
  {
    key: "search_web",
    label: "Search the web",
    hint: "How many times per turn the agent may search the web (1–50).",
  },
  {
    key: "import_web_page",
    label: "Import a web page",
    hint: "How many times per turn the agent (admins only) may import a found page into the library (1–50).",
  },
  {
    key: "prepare_final_answer",
    label: "Prepare final answer",
    hint: "How many times per turn the agent may hand off to the final-answer step (1–50).",
  },
];

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

// Per-tool call budgets for the ReAct agent (renders inside the Manage content card).
export default function AgentToolLimitsSection({ configurationVersion = 0, onConfigurationChanged }) {
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
      const result = await getAgentToolLimits();
      const s = result.settings || result;
      setForm({ ...DEFAULTS, ...s });
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
    return Object.fromEntries(FIELDS.map(({ key }) => [key, Number(form[key])]));
  }

  async function handleSave(event) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await saveAgentToolLimits(payload());
      const s = result.settings || result;
      setForm({ ...DEFAULTS, ...s });
      setConnected(true);
      setNotice("Agent tool limits saved. Takes effect on the next agent turn.");
      onConfigurationChanged?.();
    } catch (saveError) {
      setError(
        connected
          ? saveError.message
          : "Backend endpoint /admin/agent-tool-limits is not reachable — settings not persisted.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <Box sx={{ py: 2 }}>
        <Skeleton variant="text" width="30%" height={20} sx={{ mb: 1 }} />
        <Skeleton variant="rounded" height={220} />
      </Box>
    );
  }

  return (
    <>
      <Box sx={{ mb: "20px", display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="subtitle2">Configuration</Typography>
          <Typography variant="h2" sx={{ fontSize: 24 }}>Agent tool limits</Typography>
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
        The ReAct agent may call each tool only a limited number of times per turn. Once a
        tool hits its budget, the agent stops offering it and moves on. Raise a limit to let the
        agent try harder before giving up; lower it to bound latency and cost.
      </Typography>

      {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Box component="form" onSubmit={handleSave} sx={{ display: "grid", gap: 2 }}>
        <SubCard title="Per-turn call budgets">
          {FIELDS.map(({ key, label, hint }) => (
            <Field key={key} label={label} hint={hint}>
              <TextField
                value={form[key]}
                onChange={(e) => set(key, e.target.value)}
                type="number"
                inputProps={{ min: 1, max: 50 }}
                size="small"
                sx={{ width: 160 }}
              />
            </Field>
          ))}
        </SubCard>

        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
          <Button variant="contained" disabled={busy} type="submit">
            {busy ? "Saving..." : "Save tool limits"}
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
