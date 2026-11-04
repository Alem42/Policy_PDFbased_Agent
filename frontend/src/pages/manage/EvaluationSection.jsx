import { useEffect, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  FormControlLabel,
  MenuItem,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import {
  getEvaluation, saveEvaluationSettings, importEvaluationCorpus, startEvaluation,
  getEvaluationRun, cancelEvaluationRun, reviewEvaluationCase, unloadLocalModels,
  saveEvidenceValidation, applyEvaluationConfiguration,
} from "../../api";
import LibraryTaskProgress, { rememberLibraryBatch } from "../../components/LibraryTaskProgress";

const ACCENT = "#214f42";
const BORDER = "#e2e5df";
const DEFAULT_MODEL = "deepseek/deepseek-v4-flash";
const ACTIVE = ["queued", "running"];

const format = (value) => (value == null ? "N/A" : `${(value * 100).toFixed(1)}%`);

// Explanations stay out of the way until the reader hovers or focuses the icon.
function Help({ text }) {
  return (
    <Tooltip title={text} placement="top" arrow enterTouchDelay={0}>
      <InfoOutlinedIcon tabIndex={0} aria-label={text}
        sx={{ fontSize: 16, color: "text.secondary", cursor: "help", verticalAlign: "middle", ml: 0.5 }} />
    </Tooltip>
  );
}

function SubCard({ title, help, action, children }) {
  return (
    <Box sx={{ ...stack, p: 2, border: `1px solid ${BORDER}`, borderRadius: 2, gap: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography variant="body2" sx={{ fontWeight: 800, color: ACCENT }}>{title}</Typography>
        {help && <Help text={help} />}
        <Box sx={{ flex: 1 }} />
        {action}
      </Box>
      {children}
    </Box>
  );
}

function Stat({ label, value, help }) {
  return (
    <Box sx={{ p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 2, minWidth: 130 }}>
      <Typography variant="caption" sx={{ color: "text.secondary" }}>
        {label}{help && <Help text={help} />}
      </Typography>
      <Typography sx={{ fontWeight: 800, fontSize: 18, whiteSpace: "nowrap" }}>{value}</Typography>
    </Box>
  );
}

function Fold({ title, children, defaultExpanded = false }) {
  return (
    <Accordion disableGutters defaultExpanded={defaultExpanded} elevation={0}
      sx={{ minWidth: 0, border: `1px solid ${BORDER}`, borderRadius: "8px !important", "&:before": { display: "none" } }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={summarySx}>
        <Typography variant="body2" sx={{ fontWeight: 700 }}>{title}</Typography>
      </AccordionSummary>
      <AccordionDetails sx={{ ...stack, gap: 1.5 }}>{children}</AccordionDetails>
    </Accordion>
  );
}

const fieldRow = { display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" };
// Grid tracks default to the min-content width, so one long answer or citation
// would stretch every card past the page; minmax(0, 1fr) lets content wrap instead.
const stack = { display: "grid", gridTemplateColumns: "minmax(0, 1fr)", minWidth: 0 };
const summarySx = { "& .MuiAccordionSummary-content": { minWidth: 0, overflow: "hidden" } };
const wrapText = { overflowWrap: "anywhere", wordBreak: "break-word" };

function CaseReview({ runId, result, review, onSaved, onError }) {
  const [score, setScore] = useState(review?.score ?? "");
  const [comment, setComment] = useState(review?.comment ?? "");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      await reviewEvaluationCase(runId, result.case_id, { score: Number(score), comment });
      onSaved();
    } catch (error) { onError(error.message); }
    finally { setBusy(false); }
  }
  return <Box sx={{ ...fieldRow, gap: 1, mt: 1 }}>
    <TextField select size="small" label="Human score" value={score} onChange={(e) => setScore(e.target.value)} sx={{ width: 150 }}>
      {[1, 2, 3, 4, 5].map((n) => <MenuItem key={n} value={n}>{n} / 5</MenuItem>)}
    </TextField>
    <Help text="1 unsupported or incorrect · 2 major errors or omissions · 3 partly correct · 4 correct with minor gaps · 5 complete and fully supported. Check the source pages before grading." />
    <TextField size="small" label="Reason / missing evidence" value={comment} onChange={(e) => setComment(e.target.value)}
      slotProps={{ htmlInput: { maxLength: 4000 } }} sx={{ flex: 1, minWidth: 200 }} />
    <Button disabled={!score || busy} onClick={save}>Save review</Button>
  </Box>;
}

function CaseResult({ run, item, onSaved, onError }) {
  const result = run.results[item.id];
  const chip = result && (result.status === "error"
    ? <Chip size="small" color="error" label="Error" />
    : <Chip size="small" color={result.gate_correct ? "success" : "warning"}
      label={`${result.actual_allow ? "Allowed" : "Blocked"} · ${result.gate_correct ? "expected" : "unexpected"}`} />);
  return (
    <Accordion disableGutters elevation={0} TransitionProps={{ unmountOnExit: true }}
      sx={{ minWidth: 0, border: `1px solid ${BORDER}`, borderRadius: "8px !important", "&:before": { display: "none" } }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={summarySx}>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center", minWidth: 0, width: "100%" }}>
          <Typography variant="body2" sx={{ fontWeight: 700, flexShrink: 0 }}>{item.id}</Typography>
          <Typography variant="body2" noWrap sx={{ flex: 1, color: "text.secondary" }}>{item.question}</Typography>
          <Box sx={{ flexShrink: 0 }}>{chip}</Box>
        </Box>
      </AccordionSummary>
      <AccordionDetails sx={{ ...stack, ...wrapText, gap: 1 }}>
        <Typography variant="body2">Expected: {item.expected_allow ? "allow" : "block"} · {item.category} · {item.split}</Typography>
        {(item.evidence || []).map((e, i) => <Typography key={i} variant="body2" sx={{ color: "text.secondary" }}>
          Gold anchor: {e.source_id}, page {e.page}: {e.quote}</Typography>)}
        {result && <>
          <Typography variant="body2">Recall@K {format(result.evidence_recall_at_k)} · Citation integrity {format(result.citation_integrity)} · TTFT {result.ttft_ms ?? "N/A"} ms · Total {result.total_ms ?? "N/A"} ms</Typography>
          {(result.evidence_reason || result.error) && <Typography variant="body2" sx={{ color: "text.secondary" }}>{result.evidence_reason || result.error}</Typography>}
          <Box sx={{ whiteSpace: "pre-wrap", ...wrapText, p: 1.5, bgcolor: "#f7f8f5", borderRadius: 1 }}>{result.answer}</Box>
          {result.judge && <Alert severity={result.judge.score >= 90 && !result.judge.uncertain ? "success" : "warning"}>Model judge {result.judge.score}/100 · {result.judge.reason}</Alert>}
          {(result.citations || []).map((cit, i) => <Typography key={i} variant="body2">[{i + 1}] {cit.title}, page {cit.page}: {cit.quote}</Typography>)}
          {(result.validation_report || result.generation_validation) && <details><summary>Evidence contract and answer validation</summary>
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 12 }}>{JSON.stringify({ retrieval: result.validation_report, generation: result.generation_validation }, null, 2)}</pre></details>}
          {result.status === "completed" && <CaseReview runId={run.id} result={result}
            review={run.reviews?.find((r) => r.case_id === item.id)} onSaved={onSaved} onError={onError} />}
        </>}
      </AccordionDetails>
    </Accordion>
  );
}

export default function EvaluationSection({ onDocumentsChanged }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ model: DEFAULT_MODEL, top_k: 6, case_ids: [] });
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [guard, setGuard] = useState(null);

  function set(field, value) { setForm((prev) => ({ ...prev, [field]: value })); }
  async function reload() {
    try { const value = await getEvaluation(); setData(value); setGuard(value.validation_settings); }
    catch (err) { setError(err.message); }
  }
  useEffect(() => {
    getEvaluation().then((value) => { setData(value); setForm(value.settings); setGuard(value.validation_settings); })
      .catch((err) => setError(err.message));
  }, []);
  useEffect(() => {
    if (!run || !ACTIVE.includes(run.status)) return;
    const timer = setInterval(() => { getEvaluationRun(run.id).then(setRun).catch((err) => setError(err.message)); }, 4000);
    return () => clearInterval(timer);
  }, [run?.id, run?.status]);

  async function action(fn) {
    setBusy(true); setError(""); setNotice("");
    try { await fn(); await reload(); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function experiment(kind) {
    await action(async () => {
      const created = await startEvaluation({ ...form, suite: "extended", case_ids: [], kind, reuse_run_id: null,
        judge_model: form.judge_model || DEFAULT_MODEL,
        parent_run_id: kind === "parameter_sweep" && run?.artifacts?.chunk_leaderboard ? run.id : null });
      setRun(await getEvaluationRun(created.id));
    });
  }
  function exportRun() {
    const blob = new Blob([JSON.stringify(run, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `evaluation-${run.id}.json`; anchor.click();
    URL.revokeObjectURL(url);
  }

  const metrics = run?.metrics || {};
  const artifacts = run?.artifacts || {};
  const running = ACTIVE.includes(run?.status);
  const corpusCount = data ? Object.keys(data.mapping).length : null;
  const caseOptions = (form.suite === "legacy" ? data?.legacy_cases : data?.cases) || [];

  return (
    <>
      <Box sx={{ mb: "20px", display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="subtitle2">Quality</Typography>
          <Typography variant="h2" sx={{ fontSize: 24 }}>Evaluation & scoring</Typography>
        </Box>
        <Box sx={{ flex: 1 }} />
        <Button variant="outlined" onClick={reload} disabled={busy}>Refresh</Button>
      </Box>
      <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
        Test the Document Analysis pipeline against a fixed corpus and question set.
        <Help text="Runs the same retrieval, evidence gate and answer generator as Document Analysis. Web search and chat history are excluded. Source-anchored checks and the optional model judge measure different things; judge scores include reasons and can be wrong." />
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}

      <Box sx={{ ...stack, gap: 2 }}>
        <SubCard title="Test corpus" help="Twelve official policy PDFs with gold answers. Imported files carry a “Test document” badge in Library and must finish indexing before a run.">
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
            <Chip label={`Documents ${corpusCount ?? "…"} / 12`} color={corpusCount === 12 ? "success" : "default"} variant="outlined" />
            <Chip label={`${data?.cases?.length ?? "…"} questions`} variant="outlined" />
            <Chip label={`GPU worker: ${data?.runtime?.loaded ? `${data.runtime.device} loaded` : "unloaded"}`} variant="outlined" />
          </Box>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
            <Button variant="outlined" disabled={busy || !data} onClick={() => action(async () => {
              const imported = await importEvaluationCorpus();
              setNotice(`${imported.documents.length} test documents registered. Wait until Library has indexed them all.`);
              onDocumentsChanged?.();
            })}>Import test documents</Button>
            <Tooltip title="Frees GPU memory now. Model weights stay on disk and load again on the next local-model call.">
              <span><Button disabled={busy} onClick={() => action(async () => {
                await unloadLocalModels(); setNotice("Local GPU worker released.");
              })}>Release local GPU models</Button></span>
            </Tooltip>
          </Box>
        </SubCard>

        <SubCard title="Baseline run" help="Scores the current configuration. Leave Cases empty to run every question in the suite.">
          <Box sx={fieldRow}>
            <TextField select label="Test suite" size="small" value={form.suite || "extended"}
              onChange={(e) => setForm({ ...form, suite: e.target.value, case_ids: [] })} sx={{ width: 220 }}>
              <MenuItem value="extended">Extended · 120 questions</MenuItem>
              <MenuItem value="legacy">Legacy · 27 questions</MenuItem>
            </TextField>
            <TextField label="Top K" type="number" size="small" value={form.top_k}
              onChange={(e) => set("top_k", Number(e.target.value))} slotProps={{ htmlInput: { min: 1, max: 12 } }} sx={{ width: 110 }} />
            <TextField select label="Cases (empty = all)" size="small" value={form.case_ids || []} slotProps={{ select: { multiple: true } }}
              onChange={(e) => set("case_ids", e.target.value)} sx={{ minWidth: 240, maxWidth: 460, flex: 1 }}>
              {caseOptions.map((c) => <MenuItem key={c.id} value={c.id}>{c.id} · {c.category} · {c.split}</MenuItem>)}
            </TextField>
          </Box>
          <Box sx={fieldRow}>
            <TextField label="Generation model (provider/model)" value={form.model || ""} onChange={(e) => set("model", e.target.value)} size="small" sx={{ minWidth: 280, flex: 1 }} />
            <TextField label="Judge model" value={form.judge_model || DEFAULT_MODEL} onChange={(e) => set("judge_model", e.target.value)} size="small" sx={{ minWidth: 280, flex: 1 }} />
          </Box>
          <Fold title="Budget & limits">
            <Box sx={fieldRow}>
              <TextField label="Max questions per API run" type="number" size="small" value={form.max_cases ?? 20} onChange={(e) => set("max_cases", Number(e.target.value))} slotProps={{ htmlInput: { min: 1, max: 120 } }} />
              <TextField label="Token budget" type="number" size="small" value={form.token_budget ?? 100000} onChange={(e) => set("token_budget", Number(e.target.value))} slotProps={{ htmlInput: { min: 1000, max: 5000000 } }} />
              <TextField label="Max API calls" type="number" size="small" value={form.max_api_calls ?? 40} onChange={(e) => set("max_api_calls", Number(e.target.value))} slotProps={{ htmlInput: { min: 1, max: 1000 } }} />
              <TextField label="Input limit per call" type="number" size="small" value={form.max_input_tokens ?? 20000} onChange={(e) => set("max_input_tokens", Number(e.target.value))} slotProps={{ htmlInput: { min: 1000, max: 500000 } }} />
              <Help text="API batches stop as soon as any limit is reached and keep completed outputs. Token figures are conservative reservations (including output allowance), so they can exceed what the provider reports. API call limits include retries." />
            </Box>
            <Box sx={fieldRow}>
              <FormControlLabel label="Optional LLM judge (extra API calls)" control={<Switch checked={!!form.judge_enabled} onChange={(e) => set("judge_enabled", e.target.checked)} />} />
              <FormControlLabel label="Allow full-document audits (large input)" control={<Switch checked={!!form.allow_full_source_audit} onChange={(e) => set("allow_full_source_audit", e.target.checked)} />} />
            </Box>
          </Fold>
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
            <Button variant="contained" disabled={busy || running} onClick={() => action(async () => {
              const created = await startEvaluation({ ...form, kind: "baseline" }); setRun(await getEvaluationRun(created.id));
            })}>Run baseline</Button>
            <Button disabled={busy} onClick={() => action(async () => { await saveEvaluationSettings(form); setNotice("Evaluation settings saved."); })}>Save settings</Button>
          </Box>
        </SubCard>

        <SubCard title="Experiments" help="Step 1 and 2 run locally on isolated indexes and call no LLM API; parameters are chosen on calibration questions and reported separately for validation and diagnostic groups. Apply a finished step-2 result to rebuild Library once, then run step 3 against the live pipeline.">
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
            <Tooltip title="Chunk budgets 256 / 384 / 512 / 768 tokens × 0 / 12.5% / 25% overlap.">
              <span><Button disabled={busy} variant="outlined" onClick={() => experiment("chunk_sweep")}>1 · Chunk size & overlap</Button></span>
            </Tooltip>
            <Tooltip title="192 combinations of Top-K, per-document quota and score thresholds; reuses the step-1 result when one is selected.">
              <span><Button disabled={busy} variant="outlined" onClick={() => experiment("parameter_sweep")}>2 · Top-K & thresholds</Button></span>
            </Tooltip>
            <Tooltip title="Runs step 1, then step 2 on its best chunk setting.">
              <span><Button disabled={busy} variant="outlined" onClick={() => experiment("retrieval_lab")}>Run 1 → 2</Button></span>
            </Tooltip>
            <Tooltip title="Live answers on sampled questions within the budget limits above.">
              <span><Button disabled={busy} variant="contained" onClick={() => experiment("validated")}>3 · Bounded answer batch</Button></span>
            </Tooltip>
          </Box>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
            <Tooltip title="Correct answers plus deliberately altered facts, to check that the evidence guard and judge catch errors. Uses API calls.">
              <span><Button disabled={busy} onClick={() => experiment("judge_controls")}>Mutation controls</Button></span>
            </Tooltip>
            <Tooltip title={form.allow_full_source_audit ? "Re-reads full source documents to audit gold labels. High token use." : "Enable “Allow full-document audits” under Budget & limits first."}>
              <span><Button disabled={busy || !form.allow_full_source_audit} onClick={() => experiment("audit")}>Full-document audit</Button></span>
            </Tooltip>
          </Box>
        </SubCard>

        {guard && <SubCard title="Evidence protection"
          help="When on, missing evidence, an invalid validator response or an unsupported answer unit blocks the answer. Document Analysis holds the draft until validation finishes, including ReAct streaming."
          action={<Chip size="small" label={guard.enabled ? "On" : "Off"} color={guard.enabled ? "success" : "default"} />}>
          <Box sx={fieldRow}>
            <FormControlLabel label="Validate every answer before release" control={<Switch checked={guard.enabled} onChange={(e) => setGuard({ ...guard, enabled: e.target.checked })} />} />
            <FormControlLabel label="Decompose multiple requirements" control={<Switch checked={guard.decompose} onChange={(e) => setGuard({ ...guard, decompose: e.target.checked })} />} />
            <FormControlLabel label="Reserve candidates per document" control={<Switch checked={guard.per_document_quota} onChange={(e) => setGuard({ ...guard, per_document_quota: e.target.checked })} />} />
          </Box>
          <Box sx={fieldRow}>
            <TextField size="small" label="Validation model" value={guard.model} onChange={(e) => setGuard({ ...guard, model: e.target.value })} sx={{ minWidth: 280, flex: 1 }} />
            <Button disabled={busy} onClick={() => action(async () => { setGuard(await saveEvidenceValidation(guard)); setNotice("Evidence protection settings saved."); })}>Save evidence protection</Button>
          </Box>
        </SubCard>}

        <SubCard title="Runs">
          {(data?.runs || []).length === 0
            ? <Typography variant="body2" sx={{ color: "text.secondary" }}>No runs yet.</Typography>
            : <TextField select size="small" label="Recent runs" value={run?.id || ""} sx={{ maxWidth: 560 }}
              onChange={(e) => action(async () => setRun(await getEvaluationRun(e.target.value)))}>
              {data.runs.map((item) => <MenuItem key={item.id} value={item.id}>
                {new Date(item.created_at).toLocaleString()} · {item.config?.kind || "baseline"} · {item.status} · {item.completed} outputs
              </MenuItem>)}
            </TextField>}

          {run && <>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
              <Typography variant="body2" sx={{ fontWeight: 800 }}>Run {run.id.slice(0, 8)}</Typography>
              <Chip size="small" label={run.status} color={run.status === "completed" ? "success" : running ? "info" : run.status === "failed" ? "error" : "default"} />
              <Typography variant="body2" sx={{ color: "text.secondary" }}>{Object.keys(run.results).length} / {run.cases.length} questions</Typography>
              <Box sx={{ flex: 1 }} />
              <Button size="small" onClick={exportRun}>Export JSON</Button>
              {running && <Button size="small" color="error" onClick={() => action(async () => {
                await cancelEvaluationRun(run.id); setRun(await getEvaluationRun(run.id));
              })}>Cancel</Button>}
            </Box>
            {run.error && <Alert severity="error">{run.error}</Alert>}
            {metrics.stage && <Alert severity="info">Stage: {metrics.stage} · Variant: {metrics.variant || "—"} · Variants {metrics.variants_completed ?? "—"}/{metrics.variants_total ?? "—"} · Questions {metrics.cases_completed ?? metrics.completed ?? metrics.audited ?? 0}/{metrics.case_count ?? metrics.cases ?? 120}</Alert>}

            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
              <Stat label="High evidence allowed" value={format(metrics.high_evidence_allow_rate)} help="Answerable questions the gate let through." />
              <Stat label="Low evidence blocked" value={format(metrics.low_evidence_block_rate)} help="Unanswerable questions the gate refused." />
              <Stat label="Evidence Recall@K" value={format(metrics.mean_evidence_recall_at_k)} />
              <Stat label="MRR" value={metrics.mean_mrr?.toFixed(3) ?? "N/A"} help="Mean reciprocal rank of the first gold chunk." />
              <Stat label="Median / P95" value={`${metrics.median_total_ms?.toFixed(0) ?? "N/A"} / ${metrics.p95_total_ms?.toFixed(0) ?? "N/A"} ms`} />
              <Stat label="Errors" value={metrics.errors ?? 0} />
              {metrics.mean_judge_score != null && <Stat label="Judge mean" value={`${metrics.mean_judge_score.toFixed(1)} / 100`}
                help={`Uncertain: ${metrics.judge_uncertain} · Blocked after generation: ${metrics.post_generation_blocked}. A model assessment, not a factual guarantee.`} />}
            </Box>

            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
              {!running && Object.keys(run.results).length < run.cases.length && <Button disabled={busy} variant="outlined" onClick={() => action(async () => {
                const created = await startEvaluation({ ...form, suite: "extended", kind: "validated", case_ids: [], reuse_run_id: run.id });
                setRun(await getEvaluationRun(created.id));
              })}>Run unfinished questions</Button>}
              {artifacts.selected_parameters && run.status === "completed" && <Tooltip title="Saves the selected parameters and re-chunks every document from its stored text (no OCR, no LLM calls). Wait for it to finish before step 3.">
                <span><Button disabled={busy} variant="contained" onClick={() => action(async () => {
                  const applied = await applyEvaluationConfiguration(run.id);
                  setForm(applied.evaluation_settings);
                  rememberLibraryBatch("rechunk", applied.task_ids || []);
                  setNotice(`Configuration applied. Re-chunking ${applied.queued} documents (no LLM calls).`);
                  setGuard((await getEvaluation()).validation_settings); onDocumentsChanged?.();
                })}>Apply configuration & rebuild Library</Button></span>
              </Tooltip>}
            </Box>

            <LibraryTaskProgress />
            {artifacts.selected_parameters && <Alert severity="success">Selected: {JSON.stringify(artifacts.selected_parameters.parameters)} · complete evidence {format(artifacts.selected_parameters.calibration.complete_evidence_rate)} calibration / {format(artifacts.selected_parameters.validation.complete_evidence_rate)} validation
              <Help text="Score replay excludes the LLM answerability and claim checks; step 3 tests the complete live pipeline." /></Alert>}
            {artifacts.controls_summary && <Alert severity={artifacts.controls_summary.guard_correct === artifacts.controls_summary.controls ? "success" : "warning"}>Mutation controls: guard {artifacts.controls_summary.guard_correct}/{artifacts.controls_summary.controls} · judge {artifacts.controls_summary.judge_correct}/{artifacts.controls_summary.controls}</Alert>}
            {artifacts.audit_summary && <Alert severity="info">Source audit: {artifacts.audit_summary.cases} cases · label disagreements {artifacts.audit_summary.label_disagreements.length} · invalid quotes {artifacts.audit_summary.invalid_quotes.length} · uncertain {artifacts.audit_summary.uncertain.length}</Alert>}
            {artifacts.api_budget && <Alert severity={artifacts.api_budget.budget_exhausted ? "warning" : "info"}>API calls {artifacts.api_budget.api_calls}/{artifacts.api_budget.api_call_limit} · token reservations {artifacts.api_budget.reserved_tokens}/{artifacts.api_budget.estimated_token_limit}</Alert>}

            {artifacts.chunk_leaderboard && <Fold title="Chunk experiment results" defaultExpanded>
              <Box sx={{ overflowX: "auto" }}>
                <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 14 }}>
                  <thead><tr>{["Budget / overlap", "Chunks", "Max tokens", "Calibration", "Validation", "Diagnostic", "Context tokens"].map((h) =>
                    <th key={h} style={{ padding: 8, textAlign: "left" }}>{h}</th>)}</tr></thead>
                  <tbody>{artifacts.chunk_leaderboard.map((e) => <tr key={e.variant}>{[e.variant, e.stats.chunks, e.stats.max_chunk_tokens,
                    format(e.calibration.complete_evidence_rate), format(e.validation.complete_evidence_rate), format(e.diagnostic.complete_evidence_rate),
                    e.calibration.mean_context_tokens.toFixed(0)].map((v, i) => <td key={i} style={{ padding: 8, borderTop: `1px solid ${BORDER}` }}>{v}</td>)}</tr>)}</tbody>
                </table>
              </Box>
            </Fold>}

            <Fold title="Frozen settings and source snapshot">
              <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 12, margin: 0 }}>{JSON.stringify({ request: run.config, snapshot: run.snapshot, split_metrics: artifacts.by_split }, null, 2)}</pre>
            </Fold>

            <Typography variant="body2" sx={{ fontWeight: 800, mt: 1 }}>Questions</Typography>
            <Box sx={{ ...stack, gap: 1 }}>
              {run.cases.map((item) => <CaseResult key={`${run.id}-${item.id}`} run={run} item={item} onError={setError}
                onSaved={() => { getEvaluationRun(run.id).then(setRun).catch((err) => setError(err.message)); setNotice("Human review saved."); }} />)}
            </Box>
          </>}
        </SubCard>
      </Box>
    </>
  );
}
