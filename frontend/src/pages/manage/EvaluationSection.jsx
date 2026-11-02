import { useEffect, useState } from "react";
import { Alert, Box, Button, Chip, MenuItem, TextField, Typography, Switch, FormControlLabel } from "@mui/material";
import {
  getEvaluation, saveEvaluationSettings, importEvaluationCorpus, startEvaluation,
  getEvaluationRun, cancelEvaluationRun, reviewEvaluationCase, unloadLocalModels,
  saveEvidenceValidation, applyEvaluationConfiguration,
} from "../../api";

const format = (value) => value == null ? "N/A" : `${(value * 100).toFixed(1)}%`;

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
  return <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mt: 2 }}>
    <TextField select size="small" label="Human score" value={score} onChange={(e) => setScore(e.target.value)} sx={{ width: 170 }}>
      {[1, 2, 3, 4, 5].map((n) => <MenuItem key={n} value={n}>{n} / 5</MenuItem>)}
    </TextField>
    <TextField size="small" label="Reason / missing evidence" value={comment} onChange={(e) => setComment(e.target.value)} inputProps={{ maxLength: 4000 }} sx={{ flex: 1, minWidth: 200 }} />
    <Button disabled={!score || busy} onClick={save}>Save review</Button>
  </Box>;
}

export default function EvaluationSection({ onDocumentsChanged }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ model: "deepseek/deepseek-v4-flash", top_k: 6, case_ids: [] });
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [guard, setGuard] = useState(null);
  async function reload() {
    try { const value = await getEvaluation(); setData(value); setGuard(value.validation_settings); }
    catch (err) { setError(err.message); }
  }
  useEffect(() => {
    getEvaluation().then((value) => { setData(value); setForm(value.settings); setGuard(value.validation_settings); }).catch((err) => setError(err.message));
  }, []);
  useEffect(() => {
    if (!run || !["queued", "running"].includes(run.status)) return;
    const timer = setInterval(() => {
      getEvaluationRun(run.id).then(setRun).catch((err) => setError(err.message));
    }, 4000);
    return () => clearInterval(timer);
  }, [run?.id, run?.status]);
  async function action(fn) {
    setBusy(true); setError(""); setNotice("");
    try { await fn(); await reload(); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  const metrics = run?.metrics || {};
  const artifacts = run?.artifacts || {};
  async function experiment(kind) {
    await action(async () => {
      const created = await startEvaluation({ ...form, suite: "extended", case_ids: [], kind, reuse_run_id: null,
        judge_model: form.judge_model || "deepseek/deepseek-v4-flash",
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
  return <Box sx={{ display: "grid", gap: 2 }}>
    <Typography variant="h2" sx={{ fontSize: 24 }}>Evaluation & scoring</Typography>
    <Typography>Run the same retrieval, evidence gate and answer generator used by Document Analysis. Web search and chat history are excluded from this baseline.</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    {notice && <Alert severity="success">{notice}</Alert>}
    <Alert severity="info">Source-anchored tests and a stronger model judge measure different things. Judge scores include reasons and can be wrong; quote checks, mutation controls and per-requirement coverage remain visible. Human review is optional.</Alert>
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
      <Button variant="outlined" disabled={busy || !data} onClick={() => action(async () => {
        const imported = await importEvaluationCorpus();
        setNotice(`${imported.documents.length} test documents registered. Processing continues in Library; wait until all are indexed.`);
        onDocumentsChanged?.();
      })}>Import official test documents</Button>
      <Button onClick={reload}>Refresh</Button>
      <Button disabled={busy} onClick={() => action(async () => { await unloadLocalModels(); setNotice("Local GPU worker released. Weights remain installed on disk."); })}>Release local GPU models</Button>
    </Box>
    <Typography variant="body2">Corpus: {data ? Object.keys(data.mapping).length : "…"} / 12 documents · {data?.cases?.length ?? "…"} cases · GPU worker: {data?.runtime?.loaded ? `${data.runtime.device} loaded` : "unloaded"}. Test PDFs carry a “Test document” badge in Library.</Typography>
    <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
      <TextField select label="Test suite" size="small" value={form.suite || "extended"}
        onChange={(e) => setForm({ ...form, suite: e.target.value, case_ids: [] })} sx={{ width: 220 }}>
        <MenuItem value="extended">Extended · 120 questions</MenuItem><MenuItem value="legacy">Legacy · 27 questions</MenuItem>
      </TextField>
      <TextField label="Generation model (provider/model)" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} size="small" sx={{ minWidth: 300 }} />
      <TextField label="Judge model" value={form.judge_model || "deepseek/deepseek-v4-flash"} onChange={(e) => setForm({ ...form, judge_model: e.target.value })} size="small" sx={{ minWidth: 300 }} />
      <TextField label="Top K" type="number" size="small" value={form.top_k} onChange={(e) => setForm({ ...form, top_k: Number(e.target.value) })} inputProps={{ min: 1, max: 12 }} sx={{ width: 120 }} />
      <TextField select label="Cases (empty = all)" size="small" value={form.case_ids} SelectProps={{ multiple: true }}
        onChange={(e) => setForm({ ...form, case_ids: e.target.value })} sx={{ minWidth: 260, maxWidth: 500 }}>
        {((form.suite === "legacy" ? data?.legacy_cases : data?.cases) || []).map((c) => <MenuItem key={c.id} value={c.id}>{c.id} · {c.category} · {c.split}</MenuItem>)}
      </TextField>
    </Box>
    <Box sx={{ display: "flex", gap: 1 }}>
      <Button disabled={busy} onClick={() => action(async () => { await saveEvaluationSettings(form); setNotice("Evaluation settings saved."); })}>Save scoring settings</Button>
      <Button variant="contained" disabled={busy || ["queued", "running"].includes(run?.status)} onClick={() => action(async () => {
        const created = await startEvaluation({ ...form, kind: "baseline" }); setRun(await getEvaluationRun(created.id));
      })}>Run baseline</Button>
    </Box>
    <Box sx={{ border: "1px solid #dde3dc", borderRadius: 2, p: 2, display: "grid", gap: 1.5 }}>
      <Typography variant="h6">One-click experiments</Typography>
      <Typography variant="body2">Step 1 uses isolated indexes: 256 / 384 / 512 / 768 tokens × 0 / 12.5% / 25% overlap. Step 2 compares 192 Top-K, quota and score configurations. Settings are selected on calibration facts; validation and diagnostic groups are reported separately. Existing index caches may be reused; trial queries are rerun.</Typography>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
        <Button disabled={busy} variant="outlined" onClick={() => experiment("chunk_sweep")}>1 · Compare chunk sizes & overlap</Button>
        <Button disabled={busy} variant="outlined" onClick={() => experiment("parameter_sweep")}>2 · Compare Top-K & thresholds</Button>
        <Button disabled={busy} variant="outlined" onClick={() => experiment("retrieval_lab")}>Run 1 → 2</Button>
        <Button disabled={busy || !form.allow_full_source_audit} onClick={() => experiment("audit")}>Full-document audit (high token use)</Button>
        <Button disabled={busy} onClick={() => experiment("judge_controls")}>Budgeted mutation controls</Button>
        <Button disabled={busy} variant="contained" onClick={() => experiment("validated")}>3 · Run bounded answer batch</Button>
      </Box>
      <Typography variant="body2">Apply a completed parameter experiment to rebuild Library once, then run step 3. Real API calls use your configured keys. Mutation controls include correct answers and deliberate factual changes; the optional judge adds API calls.</Typography>
    </Box>
    <Alert severity="info">Local chunk / parameter experiments use no LLM API. API batches default to Flash, at most 20 sampled questions, optional scoring OFF and explicit token/call limits. Reaching a limit stops further requests and preserves completed outputs.</Alert>
    <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
      <FormControlLabel label="Enable optional LLM judge (extra API calls)" control={<Switch checked={!!form.judge_enabled} onChange={(e) => setForm({ ...form, judge_enabled: e.target.checked })} />} />
      <TextField label="Max questions per API run" type="number" size="small" value={form.max_cases ?? 20} onChange={(e) => setForm({ ...form, max_cases: Number(e.target.value) })} inputProps={{ min: 1, max: 120 }} />
      <TextField label="Conservative token budget" type="number" size="small" value={form.token_budget ?? 100000} onChange={(e) => setForm({ ...form, token_budget: Number(e.target.value) })} inputProps={{ min: 1000, max: 5000000 }} />
      <TextField label="Max API calls (includes retries)" type="number" size="small" value={form.max_api_calls ?? 40} onChange={(e) => setForm({ ...form, max_api_calls: Number(e.target.value) })} inputProps={{ min: 1, max: 1000 }} />
      <TextField label="Conservative input limit per call" type="number" size="small" value={form.max_input_tokens ?? 20000} onChange={(e) => setForm({ ...form, max_input_tokens: Number(e.target.value) })} inputProps={{ min: 1000, max: 500000 }} />
      <FormControlLabel label="Allow full-document audits (large input)" control={<Switch checked={!!form.allow_full_source_audit} onChange={(e) => setForm({ ...form, allow_full_source_audit: e.target.checked })} />} />
    </Box>
    {guard && <Box sx={{ border: "1px solid #dde3dc", borderRadius: 2, p: 2, display: "grid", gap: 1 }}>
      <Typography variant="h6">Evidence protection</Typography>
      <FormControlLabel label="Require complete evidence and validate every answer before release"
        control={<Switch checked={guard.enabled} onChange={(e) => setGuard({ ...guard, enabled: e.target.checked })} />} />
      <FormControlLabel label="Decompose multiple requirements" control={<Switch checked={guard.decompose} onChange={(e) => setGuard({ ...guard, decompose: e.target.checked })} />} />
      <FormControlLabel label="Reserve candidates across selected documents" control={<Switch checked={guard.per_document_quota} onChange={(e) => setGuard({ ...guard, per_document_quota: e.target.checked })} />} />
      <Typography variant="body2">When enabled, missing evidence, an invalid validator response, or an unsupported answer unit blocks the answer. Document Analysis buffers the draft until validation finishes, including ReAct streaming.</Typography>
      <TextField size="small" label="Validation model" value={guard.model} onChange={(e) => setGuard({ ...guard, model: e.target.value })} />
      <Button disabled={busy} onClick={() => action(async () => { setGuard(await saveEvidenceValidation(guard)); setNotice("Evidence protection settings saved."); })}>Save evidence protection</Button>
    </Box>}
    <Typography variant="h6">Recent runs</Typography>
    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
      {(data?.runs || []).map((item) => <Button key={item.id} variant={item.id === run?.id ? "contained" : "outlined"}
        onClick={() => action(async () => setRun(await getEvaluationRun(item.id)))}>
        {new Date(item.created_at).toLocaleString()} · {item.config?.kind || "baseline"} · {item.status} · {item.completed} outputs
      </Button>)}
    </Box>
    {run && <>
      <Typography variant="h6">Run {run.id.slice(0, 8)} · {run.status} · {Object.keys(run.results).length} / {run.cases.length}</Typography>
      {run.error && <Alert severity="error">{run.error}</Alert>}
      {metrics.stage && <Alert severity="info">Stage: {metrics.stage} · Variant: {metrics.variant || "—"} · Variants {metrics.variants_completed ?? "—"}/{metrics.variants_total ?? "—"} · Questions {metrics.cases_completed ?? metrics.completed ?? metrics.audited ?? 0}/{metrics.case_count ?? metrics.cases ?? 120}</Alert>}
      <Typography variant="body2">High evidence allowed: {format(metrics.high_evidence_allow_rate)} · Low evidence blocked: {format(metrics.low_evidence_block_rate)} · Evidence Recall@K: {format(metrics.mean_evidence_recall_at_k)} · MRR: {metrics.mean_mrr?.toFixed(3) ?? "N/A"} · Median: {metrics.median_total_ms?.toFixed(0) ?? "N/A"} ms · P95: {metrics.p95_total_ms?.toFixed(0) ?? "N/A"} ms · Errors: {metrics.errors ?? 0}</Typography>
      <Box><Button onClick={exportRun}>Export full JSON</Button>
        {!["queued", "running"].includes(run.status) && Object.keys(run.results).length < run.cases.length && <Button disabled={busy} onClick={() => action(async () => {
          const created = await startEvaluation({ ...form, suite: "extended", kind: "validated", case_ids: [], reuse_run_id: run.id });
          setRun(await getEvaluationRun(created.id));
        })}>Run unfinished cases only (within budget)</Button>}
        {artifacts.selected_parameters && run.status === "completed" && <Button disabled={busy} onClick={() => action(async () => {
          const applied = await applyEvaluationConfiguration(run.id);
          setForm(applied.evaluation_settings);
          setNotice(`Configuration applied. ${applied.queued} documents queued for full rebuild; wait for Library to finish before step 3.`);
          setGuard((await getEvaluation()).validation_settings); onDocumentsChanged?.();
        })}>Apply selected configuration & rebuild Library</Button>}
        {["queued", "running"].includes(run.status) && <Button onClick={() => action(async () => {
          await cancelEvaluationRun(run.id); setRun(await getEvaluationRun(run.id));
        })}>Cancel run</Button>}
      </Box>
      {artifacts.chunk_leaderboard && <Box sx={{ overflowX: "auto" }}>
        <Typography variant="h6">Chunk experiment results</Typography>
        <table style={{ borderCollapse: "collapse", width: "100%" }}><thead><tr>{["Budget / overlap", "Chunks", "Max tokens", "Calibration complete", "Validation complete", "Diagnostic complete", "Context tokens"].map((h) => <th key={h} style={{ padding: 8, textAlign: "left" }}>{h}</th>)}</tr></thead>
          <tbody>{artifacts.chunk_leaderboard.map((e) => <tr key={e.variant}>{[e.variant, e.stats.chunks, e.stats.max_chunk_tokens, format(e.calibration.complete_evidence_rate), format(e.validation.complete_evidence_rate), format(e.diagnostic.complete_evidence_rate), e.calibration.mean_context_tokens.toFixed(0)].map((v, i) => <td key={i} style={{ padding: 8, borderTop: "1px solid #dde3dc" }}>{v}</td>)}</tr>)}</tbody>
        </table>
      </Box>}
      {artifacts.selected_parameters && <Alert severity="success">Selected parameters: {JSON.stringify(artifacts.selected_parameters.parameters)} · Calibration complete evidence: {format(artifacts.selected_parameters.calibration.complete_evidence_rate)} · Validation complete evidence: {format(artifacts.selected_parameters.validation.complete_evidence_rate)}. Score replay excludes the LLM answerability/claim checks; step 3 tests the complete live pipeline.</Alert>}
      {artifacts.controls_summary && <Alert severity={artifacts.controls_summary.guard_correct === artifacts.controls_summary.controls ? "success" : "warning"}>Mutation controls: guard {artifacts.controls_summary.guard_correct}/{artifacts.controls_summary.controls}; judge {artifacts.controls_summary.judge_correct}/{artifacts.controls_summary.controls}.</Alert>}
      {artifacts.audit_summary && <Alert severity="info">Source audit: {artifacts.audit_summary.cases} cases; label disagreements {artifacts.audit_summary.label_disagreements.length}; invalid literal quotes {artifacts.audit_summary.invalid_quotes.length}; uncertain {artifacts.audit_summary.uncertain.length}. Export JSON for the complete evidence.</Alert>}
      {metrics.mean_judge_score != null && <Typography>Strong-model judge mean: {metrics.mean_judge_score.toFixed(1)}/100 · Uncertain: {metrics.judge_uncertain} · Answers blocked after generation: {metrics.post_generation_blocked}. This is a model assessment, not a factual guarantee.</Typography>}
      <details><summary>Frozen settings and source snapshot</summary><pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{JSON.stringify({ request: run.config, snapshot: run.snapshot, split_metrics: artifacts.by_split }, null, 2)}</pre></details>
      {artifacts.api_budget && <Alert severity={artifacts.api_budget.budget_exhausted ? "warning" : "info"}>API calls {artifacts.api_budget.api_calls}/{artifacts.api_budget.api_call_limit} · Conservative reservations {artifacts.api_budget.reserved_tokens}/{artifacts.api_budget.estimated_token_limit}. Reservations include output allowance and may exceed actual reported usage.</Alert>}
      <Typography variant="body2">Human rubric: 1 unsupported/incorrect · 2 major errors or omissions · 3 partly correct · 4 correct with minor gaps · 5 complete and fully supported. Check source pages before grading.</Typography>
      {run.cases.map((c) => {
        const result = run.results[c.id];
        return <Box component="details" key={`${run.id}-${c.id}`} sx={{ border: "1px solid #dde3dc", borderRadius: 1, p: 1.5 }}>
          <Box component="summary" sx={{ cursor: "pointer" }}>
            {c.id} · {c.question} {result && <Chip size="small" sx={{ ml: 1 }}
              color={result.status === "error" ? "error" : result.gate_correct ? "success" : "warning"}
              label={result.status === "error" ? "Error" : `${result.actual_allow ? "Allowed" : "Blocked"} · ${result.gate_correct ? "expected" : "unexpected"}`} />}
          </Box>
          <Typography variant="body2" sx={{ mt: 1 }}>Expected: {c.expected_allow ? "allow" : "block"} · {c.category} · {c.split}</Typography>
          {(c.evidence || []).map((e, i) => <Typography key={i} variant="body2">Gold anchor: {e.source_id}, PDF page {e.page}: {e.quote}</Typography>)}
          {result && <>
            <Typography variant="body2">Recall@K {format(result.evidence_recall_at_k)} · Citation integrity {format(result.citation_integrity)} · TTFT {result.ttft_ms ?? "N/A"} ms · Total {result.total_ms ?? "N/A"} ms</Typography>
            <Typography variant="body2" sx={{ color: "text.secondary" }}>{result.evidence_reason || result.error}</Typography>
            <Box sx={{ whiteSpace: "pre-wrap", my: 2 }}>{result.answer}</Box>
            {result.judge && <Alert severity={result.judge.score >= 90 && !result.judge.uncertain ? "success" : "warning"}>Model judge {result.judge.score}/100 · {result.judge.reason}</Alert>}
            {(result.validation_report || result.generation_validation) && <details><summary>Evidence contract and answer validation</summary><pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{JSON.stringify({ retrieval: result.validation_report, generation: result.generation_validation }, null, 2)}</pre></details>}
            {(result.citations || []).map((cit, i) => <Typography key={i} variant="body2" sx={{ mb: 1 }}>[{i+1}] {cit.title}, page {cit.page}: {cit.quote}</Typography>)}
            {result.status === "completed" && <CaseReview key={`${run.id}-${c.id}`} runId={run.id} result={result}
              review={run.reviews?.find((r) => r.case_id === c.id)} onError={setError}
              onSaved={() => { getEvaluationRun(run.id).then(setRun).catch((err) => setError(err.message)); setNotice("Human review saved."); }} />}
          </>}
        </Box>;
      })}
    </>}
  </Box>;
}
