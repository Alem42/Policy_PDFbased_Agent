import { useEffect, useMemo, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  FormControlLabel,
  LinearProgress,
  MenuItem,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { getApiBudget, getApiUsage, saveApiBudget } from "../../api";

const ACCENT = "#214f42";
const BORDER = "#e2e5df";
const PROVIDER_COLORS = { deepseek: "#3d6fb4", zhipu: "#214f42" };
const FALLBACK_COLORS = ["#c08a2b", "#8a5aa8", "#5b8c85", "#9a9a9a"];
const RANGES = [["24h", "24 h"], ["7d", "7 days"], ["30d", "30 days"], ["90d", "90 days"], ["365d", "1 year"]];
const METRICS = {
  cost: { label: "Cost (¥)", value: (r) => r.cost, format: (v) => money(v) },
  tokens: { label: "Tokens", value: (r) => r.input_tokens + r.output_tokens, format: (v) => formatNumber(v) },
  requests: { label: "Requests", value: (r) => r.requests, format: (v) => formatNumber(v) },
};
const OPERATION_LABELS = {
  answer: "Chat answer",
  evidence_validation: "Evidence validation",
  evidence_gate: "Evidence gate",
  suggestions: "Follow-up suggestions",
  metadata: "Metadata extraction",
  contextual_header: "Contextual headers",
  ingest: "Document ingest",
  rechunk: "Re-chunk",
  reembed: "Re-embed",
  connection_test: "Connection test",
};
const stack = { display: "grid", gridTemplateColumns: "minmax(0, 1fr)", minWidth: 0 };

// Small enough to read either way: ¥0.000021, ¥0.4310, ¥12.50.
function money(value) {
  const v = Number(value || 0);
  if (v === 0) return "¥0";
  if (v < 0.01) return `¥${v.toPrecision(2)}`;
  return `¥${v.toFixed(v < 1 ? 4 : 2)}`;
}

function formatNumber(value) {
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}k`;
  return String(Math.round(value));
}

function Help({ text }) {
  return (
    <Tooltip title={text} arrow enterTouchDelay={0}>
      <InfoOutlinedIcon tabIndex={0} aria-label={text}
        sx={{ fontSize: 16, color: "text.secondary", cursor: "help", verticalAlign: "middle", ml: 0.5 }} />
    </Tooltip>
  );
}

function SubCard({ title, help, action, children }) {
  return (
    <Box sx={{ ...stack, p: 2, border: `1px solid ${BORDER}`, borderRadius: 2, gap: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Typography variant="body2" sx={{ fontWeight: 800, color: ACCENT }}>{title}</Typography>
        {help && <Help text={help} />}
        <Box sx={{ flex: 1 }} />
        {action}
      </Box>
      {children}
    </Box>
  );
}

function Stat({ label, value, sub }) {
  return (
    <Box sx={{ p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 2, minWidth: 140, flex: "1 1 140px" }}>
      <Typography variant="caption" sx={{ color: "text.secondary" }}>{label}</Typography>
      <Typography sx={{ fontWeight: 800, fontSize: 20, whiteSpace: "nowrap" }}>{value}</Typography>
      {sub && <Typography variant="caption" sx={{ color: "text.secondary" }}>{sub}</Typography>}
    </Box>
  );
}

// Every bucket in the range, in the browser's time zone, matching the API's
// "YYYY-MM-DDTHH:MM:SS" local timestamps, so empty hours/days still show.
function bucketKeys(since, bucket) {
  const pad = (n) => String(n).padStart(2, "0");
  const key = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00:00`;
  const cursor = new Date(since);
  if (bucket === "hour") cursor.setMinutes(0, 0, 0);
  else if (bucket === "day") cursor.setHours(0, 0, 0, 0);
  else { cursor.setDate(1); cursor.setHours(0, 0, 0, 0); }
  const keys = [];
  const now = new Date();
  while (cursor <= now && keys.length < 400) {
    keys.push(key(cursor));
    if (bucket === "hour") cursor.setHours(cursor.getHours() + 1);
    else if (bucket === "day") cursor.setDate(cursor.getDate() + 1);
    else cursor.setMonth(cursor.getMonth() + 1);
  }
  return keys;
}

function bucketLabel(key, bucket) {
  const [date, time] = key.split("T");
  const [, month, day] = date.split("-");
  if (bucket === "hour") return time.slice(0, 5);
  if (bucket === "month") return `${date.slice(0, 7)}`;
  return `${Number(month)}/${Number(day)}`;
}

function UsageChart({ data, metric }) {
  const { value, format } = METRICS[metric];
  const providers = useMemo(() => [...new Set(data.series.map((r) => r.provider))].sort(), [data]);
  const colors = Object.fromEntries(providers.map((p, i) => [p, PROVIDER_COLORS[p] || FALLBACK_COLORS[i % FALLBACK_COLORS.length]]));
  const keys = useMemo(() => bucketKeys(data.since, data.bucket), [data]);
  const byBucket = useMemo(() => {
    const map = {};
    for (const row of data.series) {
      const k = row.bucket.slice(0, 19);
      (map[k] ||= {})[row.provider] = value(row);
    }
    return map;
  }, [data, value]);
  const totals = keys.map((k) => providers.reduce((sum, p) => sum + (byBucket[k]?.[p] || 0), 0));
  const max = Math.max(...totals, 0);
  const width = 760;
  const height = 220;
  const left = 76;
  const bottom = 26;
  const plotW = width - left - 8;
  const plotH = height - bottom - 10;
  const barW = Math.max(plotW / Math.max(keys.length, 1) - 2, 1);
  const labelEvery = Math.ceil(keys.length / 12);

  if (!data.series.length) {
    return <Typography variant="body2" sx={{ color: "text.secondary", py: 4, textAlign: "center" }}>No paid API calls in this period.</Typography>;
  }
  return (
    <Box sx={{ ...stack, gap: 1 }}>
      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
        {providers.map((p) => (
          <Box key={p} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
            <Box sx={{ width: 10, height: 10, borderRadius: "2px", bgcolor: colors[p] }} />
            <Typography variant="caption">{p}</Typography>
          </Box>
        ))}
      </Box>
      <Box component="svg" viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={`${METRICS[metric].label} per ${data.bucket}`} sx={{ width: "100%", height: "auto" }}>
        {[0, 0.5, 1].map((f) => {
          const y = 10 + plotH * (1 - f);
          return (
            <g key={f}>
              <line x1={left} x2={width - 8} y1={y} y2={y} stroke="#e6e9e4" />
              <text x={left - 6} y={y + 4} textAnchor="end" fontSize="11" fill="#6b7280">{max ? format(max * f) : "0"}</text>
            </g>
          );
        })}
        {keys.map((k, i) => {
          let y = 10 + plotH;
          const x = left + i * (plotW / keys.length) + 1;
          return (
            <g key={k}>
              {providers.map((p) => {
                const v = byBucket[k]?.[p] || 0;
                if (!v || !max) return null;
                const h = (v / max) * plotH;
                y -= h;
                return (
                  <rect key={p} x={x} y={y} width={barW} height={Math.max(h, 1)} fill={colors[p]} rx="1.5">
                    <title>{`${bucketLabel(k, data.bucket)} · ${p}: ${format(v)}`}</title>
                  </rect>
                );
              })}
              {i % labelEvery === 0 && (
                <text x={x + barW / 2} y={height - 8} textAnchor="middle" fontSize="11" fill="#6b7280">{bucketLabel(k, data.bucket)}</text>
              )}
            </g>
          );
        })}
      </Box>
    </Box>
  );
}

function Table({ columns, rows, empty = "No data." }) {
  if (!rows.length) return <Typography variant="body2" sx={{ color: "text.secondary" }}>{empty}</Typography>;
  return (
    <Box sx={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 14 }}>
        <thead>
          <tr>{columns.map((c) => <th key={c.label} style={{ textAlign: c.align || "left", padding: "6px 8px", color: "#6b7280", fontWeight: 600 }}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => <td key={c.label} style={{ textAlign: c.align || "left", padding: "6px 8px", borderTop: `1px solid ${BORDER}`, whiteSpace: c.nowrap ? "nowrap" : "normal" }}>{c.render(row)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </Box>
  );
}


const measureColumns = [
  { label: "Cost", align: "right", nowrap: true, render: (r) => money(r.cost) },
  { label: "Input tokens", align: "right", render: (r) => formatNumber(r.input_tokens) },
  { label: "Output tokens", align: "right", render: (r) => formatNumber(r.output_tokens) },
  { label: "Requests", align: "right", render: (r) => formatNumber(r.requests) },
];

function BudgetCard({ view, onSaved, onError }) {
  const [form, setForm] = useState(view.settings);
  const [busy, setBusy] = useState(false);
  useEffect(() => setForm(view.settings), [view]);
  const set = (field, value) => setForm((prev) => ({ ...prev, [field]: value }));
  const setPrice = (key, field, value) =>
    setForm((prev) => ({ ...prev, prices: { ...prev.prices, [key]: { ...prev.prices[key], [field]: Number(value) } } }));
  async function save() {
    setBusy(true);
    try {
      onSaved(await saveApiBudget({ ...form, limit_cny: form.limit_cny === "" || form.limit_cny == null ? null : Number(form.limit_cny) }));
    } catch (error) {
      onError(error.message);
    } finally {
      setBusy(false);
    }
  }
  const ratio = view.used_ratio ?? 0;
  return (
    <SubCard title="Budget"
      help="When enabled and the limit is reached, every paid chat, embedding, rerank and web-search request is refused before it is sent (HTTP 429). Local models keep working. Costs are computed from the prices below."
      action={<Chip size="small" label={view.blocking ? "Limit reached — paid APIs blocked" : form.enabled ? "Enforced" : "Not enforced"}
        color={view.blocking ? "error" : form.enabled ? "success" : "default"} />}>
      <Box sx={{ display: "grid", gap: 0.75 }}>
        <Typography variant="body2">
          {money(view.spent_cny)} spent this {form.period === "month" ? "month" : "period (all time)"}
          {view.settings.limit_cny != null && <> of {money(view.settings.limit_cny)} · {money(view.remaining_cny)} left</>}
        </Typography>
        {view.settings.limit_cny != null && (
          <LinearProgress variant="determinate" value={Math.round(ratio * 100)} color={ratio >= 1 ? "error" : ratio >= 0.8 ? "warning" : "primary"}
            sx={{ height: 8, borderRadius: 999 }} />
        )}
      </Box>
      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
        <FormControlLabel label="Enforce the limit" control={<Switch checked={!!form.enabled} onChange={(e) => set("enabled", e.target.checked)} />} />
        <TextField label="Limit (¥)" type="number" size="small" value={form.limit_cny ?? ""} onChange={(e) => set("limit_cny", e.target.value)}
          slotProps={{ htmlInput: { min: 0, step: 1 } }} sx={{ width: 150 }} />
        <TextField select label="Period" size="small" value={form.period} onChange={(e) => set("period", e.target.value)} sx={{ width: 170 }}>
          <MenuItem value="month">Calendar month</MenuItem>
          <MenuItem value="total">All time</MenuItem>
        </TextField>
        <TextField label="Time zone (months start at)" size="small" value={form.timezone} onChange={(e) => set("timezone", e.target.value)} sx={{ width: 230 }} />
      </Box>
      <Accordion disableGutters elevation={0} sx={{ border: `1px solid ${BORDER}`, borderRadius: "8px !important", "&:before": { display: "none" } }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>Prices (¥)</Typography>
          <Help text="Estimates from public price lists; confirm them on each provider's pricing page. “provider/*” applies to any model of that provider without its own row. Changing a price only affects calls recorded afterwards." />
        </AccordionSummary>
        <AccordionDetails>
          <Table rows={Object.entries(form.prices || {})} columns={[
            { label: "Provider / model", render: ([key]) => <code>{key}</code> },
            { label: "Input / 1M tokens", render: ([key, p]) => <TextField size="small" type="number" value={p.input_per_million} onChange={(e) => setPrice(key, "input_per_million", e.target.value)} slotProps={{ htmlInput: { min: 0, step: 0.1 } }} sx={{ width: 110 }} /> },
            { label: "Output / 1M tokens", render: ([key, p]) => <TextField size="small" type="number" value={p.output_per_million} onChange={(e) => setPrice(key, "output_per_million", e.target.value)} slotProps={{ htmlInput: { min: 0, step: 0.1 } }} sx={{ width: 110 }} /> },
            { label: "Per request", render: ([key, p]) => <TextField size="small" type="number" value={p.per_request} onChange={(e) => setPrice(key, "per_request", e.target.value)} slotProps={{ htmlInput: { min: 0, step: 0.01 } }} sx={{ width: 110 }} /> },
          ]} />
        </AccordionDetails>
      </Accordion>
      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
        <TextField label="Daily limit (¥)" size="small" disabled value="" placeholder="Planned" sx={{ width: 150 }} />
        <TextField label="Per user / month (¥)" size="small" disabled value="" placeholder="Planned" sx={{ width: 170 }} />
        <TextField label="Per conversation (¥)" size="small" disabled value="" placeholder="Planned" sx={{ width: 170 }} />
        <Help text="Reserved for the next version: daily, per-user and per-conversation limits. They are stored in the same settings row, so turning them on later does not change saved data." />
      </Box>
      <Box><Button variant="contained" disabled={busy} onClick={save}>{busy ? "Saving..." : "Save budget"}</Button></Box>
    </SubCard>
  );
}

export default function UsageSection() {
  const [range, setRange] = useState("7d");
  const [metric, setMetric] = useState("cost");
  const [data, setData] = useState(null);
  const [budgetView, setBudgetView] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [usage, budget] = await Promise.all([getApiUsage(range, tz), getApiBudget()]);
      setData(usage);
      setBudgetView(budget);
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, [range]);

  const totals = data?.totals;
  return (
    <>
      <Box sx={{ mb: "20px", display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="subtitle2">Cost control</Typography>
          <Typography variant="h2" sx={{ fontSize: 24 }}>API usage & budget</Typography>
        </Box>
        <Box sx={{ flex: 1 }} />
        <ToggleButtonGroup size="small" exclusive value={range} onChange={(_, v) => v && setRange(v)}>
          {RANGES.map(([value, label]) => <ToggleButton key={value} value={value}>{label}</ToggleButton>)}
        </ToggleButtonGroup>
        <Button variant="outlined" onClick={load} disabled={loading}>Refresh</Button>
      </Box>
      <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
        Every paid DeepSeek and Zhipu request, who triggered it and what it cost.
        <Help text={`Recorded since this feature was installed. Token counts come from the provider's response; costs use the prices in Budget. Times are shown in ${tz}.`} />
      </Typography>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
      {loading && !data && <LinearProgress />}

      {data && <Box sx={{ ...stack, gap: 2 }}>
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          <Stat label="Cost" value={money(totals.cost)} sub={RANGES.find(([v]) => v === range)[1]} />
          <Stat label="Input tokens" value={formatNumber(totals.input_tokens)} />
          <Stat label="Output tokens" value={formatNumber(totals.output_tokens)} />
          <Stat label="Requests" value={formatNumber(totals.requests)} />
          {budgetView?.settings.limit_cny != null && <Stat label="Budget used" value={`${Math.round((budgetView.used_ratio || 0) * 100)}%`}
            sub={`${money(budgetView.spent_cny)} of ${money(budgetView.settings.limit_cny)}`} />}
        </Box>

        <SubCard title={`Usage per ${data.bucket}`}
          action={<ToggleButtonGroup size="small" exclusive value={metric} onChange={(_, v) => v && setMetric(v)}>
            {Object.entries(METRICS).map(([key, m]) => <ToggleButton key={key} value={key}>{m.label}</ToggleButton>)}
          </ToggleButtonGroup>}>
          <UsageChart data={data} metric={metric} />
        </SubCard>

        {budgetView && <BudgetCard view={budgetView} onError={setError}
          onSaved={(view) => { setBudgetView(view); setNotice("Budget saved."); setError(""); }} />}

        <SubCard title="By model" help="Which provider and model the money went to.">
          <Table rows={data.by_model} columns={[
            { label: "Provider", render: (r) => r.provider },
            { label: "Model", render: (r) => r.model },
            { label: "Type", render: (r) => r.kind },
            ...measureColumns,
          ]} />
        </SubCard>

        <SubCard title="By feature" help="Area is the part of the product that triggered the call; step is what it was doing. Background work such as document processing has no signed-in user.">
          <Table rows={data.by_feature} columns={[
            { label: "Area", render: (r) => r.area },
            { label: "Step", render: (r) => OPERATION_LABELS[r.operation] || r.operation },
            ...measureColumns,
          ]} />
        </SubCard>

        <SubCard title="By user">
          <Table rows={data.by_user} columns={[{ label: "User", render: (r) => r.username }, ...measureColumns]} />
        </SubCard>

        <Accordion disableGutters elevation={0} sx={{ border: `1px solid ${BORDER}`, borderRadius: "8px !important", "&:before": { display: "none" } }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>Latest 50 requests</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Table rows={data.recent} columns={[
              { label: "Time", nowrap: true, render: (r) => new Date(r.created_at).toLocaleString() },
              { label: "Model", render: (r) => `${r.provider}/${r.model}` },
              { label: "Area · step", render: (r) => `${r.area} · ${OPERATION_LABELS[r.operation] || r.operation}` },
              { label: "User", render: (r) => r.username || "—" },
              { label: "In", align: "right", render: (r) => formatNumber(r.input_tokens) },
              { label: "Out", align: "right", render: (r) => formatNumber(r.output_tokens) },
              { label: "Cost", align: "right", nowrap: true, render: (r) => money(r.cost) },
            ]} />
          </AccordionDetails>
        </Accordion>
      </Box>}
    </>
  );
}
