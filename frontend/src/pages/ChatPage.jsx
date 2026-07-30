import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  Checkbox,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Drawer,
  IconButton,
  ListItemButton,
  ListItemText,
  ListSubheader,
  Menu,
  MenuItem,
  Snackbar,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import ArrowDropDownIcon from "@mui/icons-material/ArrowDropDown";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/Delete";
import EditOutlinedIcon from "@mui/icons-material/Edit";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import SendIcon from "@mui/icons-material/Send";
import StopIcon from "@mui/icons-material/Stop";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  askQuestionStream,
  deleteChatSession,
  getChatModels,
  getChatSession,
  getChatSessions,
  getDocumentChunks,
  getDocumentDetail,
  openDocumentFile,
  renameChatSession,
  resumeChatStream,
} from "../api";
import CitationList from "../components/CitationList";
import DocumentDrawer from "../components/DocumentDrawer";

// Splits text on citation markers [1], [1-3], [1, 2] and wraps in clickable <sup>
const CITATION_RE = /(\[\d+(?:[-,]\s*\d+)*\])/;

function renderWithCitations(children, citations, onOpen, lowEvidence = false) {
  return (Array.isArray(children) ? children : [children]).map((child, outerIdx) => {
    if (typeof child !== "string") return child;
    const parts = child.split(CITATION_RE);
    if (parts.length === 1) return child;
    return parts.map((part, i) => {
      if (!CITATION_RE.test(part)) return part;
      const nums = [...part.matchAll(/\d+/g)].map((m) => parseInt(m[0], 10));
      if (!nums.length) return part;
      const primaryIdx = nums[0] - 1;
      if (primaryIdx < 0 || primaryIdx >= (citations || []).length) return part;
      return (
        <sup key={`${outerIdx}-${i}`}>
          <button
            onClick={() => onOpen(citations, primaryIdx)}
            title={`Source: ${citations[primaryIdx]?.title || part}`}
            style={{
              cursor: "pointer",
              color: lowEvidence ? "#d84315" : "#214f42",
              fontWeight: 700,
              background: lowEvidence ? "rgba(216,67,21,0.08)" : "none",
              border: "none",
              borderRadius: "3px",
              padding: "0 2px",
              fontSize: "0.75em",
              lineHeight: 1,
              fontFamily: "inherit",
              textDecoration: "underline dotted",
            }}
          >
            {part}
          </button>
        </sup>
      );
    });
  });
}

function makeMarkdownComponents(citations, onOpen, lowEvidence = false) {
  return {
    p: ({ children }) => <p>{renderWithCitations(children, citations, onOpen, lowEvidence)}</p>,
    li: ({ children }) => <li>{renderWithCitations(children, citations, onOpen, lowEvidence)}</li>,
  };
}

const RESPONSE_MODE_OPTIONS = [
  {
    value: "researcher",
    label: "Policy Researcher",
    description: "Dense, specialist language for practitioners",
  },
  {
    value: "policymaker",
    label: "Policymaker",
    description: "Document-grounded analysis for policy decision preparation",
  },
  {
    value: "student",
    label: "Student",
    description: "Plain language with short explanations",
  },
];

const ANSWER_MODE_OPTIONS = [
  {
    value: "analysis",
    label: "Document Analysis",
    description: "Answer only from selected documents",
  },
  {
    value: "chat",
    label: "Open Discussion",
    description: "Discuss with general knowledge allowed",
  },
];

const AGENT_MODE_OPTIONS = [
  {
    value: "react",
    label: "Agent (ReAct)",
    description: "Multi-step reasoning with web search and a visible trace",
  },
  {
    value: "direct",
    label: "Direct",
    description: "One retrieval pass, fastest answer, no reasoning trace",
  },
];

function getOptionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || value;
}

function getResponseModeLabel(value) {
  return getOptionLabel(RESPONSE_MODE_OPTIONS, value);
}

// Flattens the /chat/models response ([{provider, provider_label, models}, ...])
// into a lookup keyed by "<provider>/<model-id>" for display purposes.
function flattenModelLabels(providerGroups) {
  const lookup = {};
  for (const group of providerGroups || []) {
    for (const model of group.models || []) {
      lookup[model.id] = `${model.label} (${group.provider_label})`;
    }
  }
  return lookup;
}

function getModelLabel(modelLookup, modelId) {
  if (!modelId) return null;
  return modelLookup[modelId] || modelId;
}

// Collapsible tool-call trace for one assistant turn, GPT-style: expanded
// while the agent is still deciding what to do, collapses to a one-line
// summary the moment the real answer starts streaming (still expandable to
// review afterward).
function ReasoningSteps({ steps, expanded, onToggle, active }) {
  if (!steps?.length) return null;
  const summary = active
    ? steps[steps.length - 1]?.label || "Working…"
    : `Reasoning · ${steps.length} step${steps.length !== 1 ? "s" : ""}`;

  return (
    <Box sx={{ mb: 1 }}>
      <Button
        size="small"
        variant="text"
        onClick={onToggle}
        startIcon={
          active ? (
            <CircularProgress size={12} thickness={6} sx={{ color: "#63706a" }} />
          ) : expanded ? (
            <ExpandLessIcon sx={{ fontSize: 16 }} />
          ) : (
            <ExpandMoreIcon sx={{ fontSize: 16 }} />
          )
        }
        sx={{
          textTransform: "none",
          color: "#63706a",
          fontSize: 12,
          fontStyle: active ? "italic" : "normal",
          py: 0.25,
          px: 0.5,
          minWidth: 0,
          "&:hover": { bgcolor: "transparent", color: "#214f42" },
        }}
      >
        {summary}
      </Button>
      <Collapse in={expanded || active}>
        <Box sx={{ pl: 1.75, ml: 0.75, mt: 0.5, borderLeft: "2px solid #e2e5df" }}>
          {steps.map((step, i) => (
            <Box
              key={`${step.tool}-${i}`}
              sx={{ display: "flex", alignItems: "flex-start", gap: 1, py: 0.55 }}
            >
              {step.status === "running" && active ? (
                <CircularProgress
                  size={12}
                  thickness={6}
                  sx={{ color: "#214f42", flexShrink: 0, mt: 0.3 }}
                />
              ) : step.status === "running" ? (
                // Stream stopped mid-call: this step never got a tool_result,
                // so show a static "stopped" mark instead of spinning forever.
                <StopIcon sx={{ fontSize: 12, flexShrink: 0, mt: 0.3, color: "#98a29c" }} />
              ) : (
                <CheckCircleOutlineIcon
                  sx={{
                    fontSize: 14,
                    flexShrink: 0,
                    mt: 0.2,
                    color: step.evidenceSufficient === false ? "#bf360c" : "#214f42",
                  }}
                />
              )}
              <Box sx={{ minWidth: 0, flex: 1 }}>
                <Typography variant="caption" sx={{ color: "#4a5a54", fontSize: 12 }}>
                  {step.label}
                  {step.status === "done" && step.evidenceSufficient === true && " — found relevant sources"}
                  {step.status === "done" && step.evidenceSufficient === false && " — not enough evidence"}
                  {step.status === "running" && !active && " — stopped"}
                </Typography>
                {(step.query || step.question || step.url) && (
                  <Typography
                    variant="caption"
                    sx={{ display: "block", pl: 0.75, color: "#6a7772", fontSize: 11.5, overflowWrap: "anywhere" }}
                  >
                    <Box component="span" sx={{ fontWeight: 600 }}>Query: </Box>
                    {step.query || step.question || step.url}
                  </Typography>
                )}
                {step.decisionReason && (
                  <Typography variant="caption" sx={{ display: "block", pl: 0.75, color: "#6a7772", fontSize: 11.5 }}>
                    <Box component="span" sx={{ fontWeight: 600 }}>Why: </Box>
                    {step.decisionReason}
                  </Typography>
                )}
                {step.status === "done" && Number.isInteger(step.resultCount) && (
                  <Typography variant="caption" sx={{ display: "block", pl: 0.75, color: "#6a7772", fontSize: 11.5 }}>
                    <Box component="span" sx={{ fontWeight: 600 }}>Result: </Box>
                    {step.resultCount} candidate source{step.resultCount === 1 ? "" : "s"}
                  </Typography>
                )}
                {step.evidenceReason && (
                  <Typography variant="caption" sx={{ display: "block", pl: 0.75, color: "#6a7772", fontSize: 11.5 }}>
                    <Box component="span" sx={{ fontWeight: 600 }}>Evidence: </Box>
                    {step.evidenceReason}
                  </Typography>
                )}
                {step.sourceTitles?.length > 0 && (
                  <Typography variant="caption" sx={{ display: "block", pl: 0.75, color: "#6a7772", fontSize: 11.5 }}>
                    <Box component="span" sx={{ fontWeight: 600 }}>Sources: </Box>
                    {step.sourceTitles.join(" · ")}
                  </Typography>
                )}
                {step.answerPlan && (
                  <Typography variant="caption" sx={{ display: "block", pl: 0.75, color: "#6a7772", fontSize: 11.5 }}>
                    <Box component="span" sx={{ fontWeight: 600 }}>Answer plan: </Box>
                    {step.answerPlan}
                  </Typography>
                )}
                {step.citationNumbers?.length > 0 && (
                  <Typography variant="caption" sx={{ display: "block", pl: 0.75, color: "#6a7772", fontSize: 11.5 }}>
                    <Box component="span" sx={{ fontWeight: 600 }}>Planned citations: </Box>
                    {step.citationNumbers.map((number) => `[${number}]`).join(", ")}
                  </Typography>
                )}
              </Box>
            </Box>
          ))}
        </Box>
      </Collapse>
    </Box>
  );
}

// Claude-Code-style inline permission prompt: a bordered card with a
// numbered, keyboard-selectable list of options, rendered directly in the
// chat flow instead of a modal dialog. ask_user covers three modes
// ("confirm" a yes/no gate, "choice" 2+ model-suggested candidates,
// "freeform" an open question with no options); confirm_import is a
// separate, visually flagged permanent/shared-library-changing action.
// Every mode except "freeform" also offers an "Other" row so the user isn't
// stuck picking from options they don't actually want.
function ConfirmPrompt({ confirm, busy, onAnswer }) {
  const [otherOpen, setOtherOpen] = useState(false);
  const [otherText, setOtherText] = useState("");

  // Reset the "Other" input whenever a new prompt comes in (new confirm
  // object reference each time, since it's rebuilt from a fresh SSE event).
  useEffect(() => {
    setOtherOpen(false);
    setOtherText("");
  }, [confirm]);

  if (!confirm) return null;
  const isImport = confirm.type === "confirm_import";
  const mode = isImport ? "confirm" : confirm.mode || "confirm";
  const isFreeform = mode === "freeform";
  const options = isImport
    ? [
        { value: true, label: "Yes, import this page into the knowledge base" },
        { value: false, label: "No, just answer without importing" },
      ]
    : (confirm.options || (mode === "confirm" ? ["Yes", "No"] : [])).map((option) => ({
        value: option,
        label: option,
      }));
  const accent = isImport ? "#b45309" : "#214f42";
  const accentBg = isImport ? "#fff8f0" : "#fafaf8";
  const accentBorder = isImport ? "#fcd9a8" : "#d9d8d0";
  const accentHoverBg = isImport ? "#ffedd5" : "#eef2ec";
  const header = isImport
    ? "⚠ Import into the knowledge base?"
    : mode === "choice"
      ? "Choose an option"
      : mode === "freeform"
        ? "A question for you"
        : "Search the web?";

  function submitOther() {
    const text = otherText.trim();
    if (!text || busy) return;
    onAnswer(text);
  }

  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: accentBorder,
        borderRadius: 2,
        bgcolor: accentBg,
        p: 2,
        mb: 2,
      }}
    >
      <Typography variant="body2" sx={{ fontWeight: 800, color: isImport ? accent : "inherit" }}>
        {header}
      </Typography>
      {isImport && (
        <Box sx={{ mt: 0.5, mb: 1 }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>{confirm.title}</Typography>
          <Typography variant="caption" sx={{ color: "#63706a", wordBreak: "break-all" }}>
            {confirm.url}
          </Typography>
        </Box>
      )}
      <Typography variant="body2" sx={{ color: "#4a5a54", mt: isImport ? 0 : 0.5, mb: 1.5 }}>
        {confirm.question ||
          (isImport
            ? "This permanently adds the page to the shared knowledge base — every user will be able to find it."
            : "The selected documents don't have enough information. Search the web for this answer?")}
      </Typography>

      {isFreeform ? (
        <Box sx={{ display: "flex", gap: 1 }}>
          <TextField
            size="small"
            fullWidth
            autoFocus
            placeholder="Type your answer..."
            value={otherText}
            onChange={(event) => setOtherText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submitOther();
              }
            }}
            disabled={busy}
          />
          <Button variant="contained" disabled={busy || !otherText.trim()} onClick={submitOther}>
            Send
          </Button>
        </Box>
      ) : (
        <>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
            {options.map((option, i) => (
              <Box
                key={String(option.value)}
                onClick={() => !busy && onAnswer(option.value)}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1.25,
                  px: 1.25,
                  py: 0.85,
                  borderRadius: 1.5,
                  cursor: busy ? "default" : "pointer",
                  border: "1px solid transparent",
                  opacity: busy ? 0.6 : 1,
                  "&:hover": busy ? {} : { bgcolor: accentHoverBg, borderColor: accent },
                }}
              >
                <Box
                  sx={{
                    width: 20,
                    height: 20,
                    borderRadius: "5px",
                    border: "1.5px solid",
                    borderColor: accent,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 11,
                    fontWeight: 800,
                    color: accent,
                    flexShrink: 0,
                  }}
                >
                  {i + 1}
                </Box>
                <Typography variant="body2">{option.label}</Typography>
              </Box>
            ))}
            {otherOpen ? (
              <Box sx={{ display: "flex", gap: 1, alignItems: "center", px: 1.25, py: 0.5 }}>
                <TextField
                  size="small"
                  fullWidth
                  autoFocus
                  placeholder="Type your own answer..."
                  value={otherText}
                  onChange={(event) => setOtherText(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      submitOther();
                    }
                  }}
                  disabled={busy}
                />
                <Button size="small" variant="contained" disabled={busy || !otherText.trim()} onClick={submitOther}>
                  Send
                </Button>
              </Box>
            ) : (
              <Box
                onClick={() => !busy && setOtherOpen(true)}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1.25,
                  px: 1.25,
                  py: 0.85,
                  borderRadius: 1.5,
                  cursor: busy ? "default" : "pointer",
                  border: "1px dashed",
                  borderColor: "#c7cbc2",
                  opacity: busy ? 0.6 : 1,
                  "&:hover": busy ? {} : { bgcolor: accentHoverBg, borderColor: accent },
                }}
              >
                <EditOutlinedIcon sx={{ fontSize: 16, color: "#98a29c", flexShrink: 0 }} />
                <Typography variant="body2" sx={{ color: "#6a7772" }}>
                  Other — type your own answer
                </Typography>
              </Box>
            )}
          </Box>
          <Typography variant="caption" sx={{ display: "block", mt: 1, color: "#98a29c" }}>
            Press a number key to choose.
          </Typography>
        </>
      )}
    </Box>
  );
}

function formatSessionDate(dateStr) {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return date.toLocaleDateString(undefined, { weekday: "short" });
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function ChatPage({
  documents,
  user,
  onNavigate,
  contextSourceIds = [],
  onAddSource,
  onRemoveSource,
  onSetSources,
}) {
  const location = useLocation();
  const resumeSessionId = location.state?.sessionId ?? null;

  const [selected, setSelected] = useState([]);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [responseMode, setResponseMode] = useState("researcher");
  const [answerMode, setAnswerMode] = useState("analysis");
  const [agentMode, setAgentMode] = useState("react");
  const [responseModeAnchor, setResponseModeAnchor] = useState(null);
  const [answerModeAnchor, setAnswerModeAnchor] = useState(null);
  const [agentModeAnchor, setAgentModeAnchor] = useState(null);

  // Per-message model selection: null means "use the workspace default model".
  const [modelGroups, setModelGroups] = useState([]);
  const [selectedModel, setSelectedModel] = useState(null);
  const [modelAnchor, setModelAnchor] = useState(null);
  const modelLabels = flattenModelLabels(modelGroups);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sessionId, setSessionId] = useState(resumeSessionId);
  // Set when the agent pauses on ask_user or import_web_page (confirm_import)
  // — {type, session_id, mode, question, options} or
  // {type, session_id, url, title, question}. Cleared once the user answers.
  const [pendingConfirm, setPendingConfirm] = useState(null);
  const [confirmBusy, setConfirmBusy] = useState(false);

  // History state
  const [historySessions, setHistorySessions] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: "" });
  const [renameDialog, setRenameDialog] = useState({ open: false, sessionId: null, title: "" });
  const [deleteDialog, setDeleteDialog] = useState({ open: false, sessionId: null });
  const [copiedIdx, setCopiedIdx] = useState(null);

  const [citationDrawer, setCitationDrawer] = useState({
    open: false,
    citations: [],
    focusIndex: 0,
    evidenceSufficient: true,
    evidenceReason: null,
  });

  // Document detail drawer (Sources module) — same drawer used in the Library page
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false);
  const [detailDoc, setDetailDoc] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailChunks, setDetailChunks] = useState(null);
  const [detailChunksLoading, setDetailChunksLoading] = useState(false);
  const [openChunkId, setOpenChunkId] = useState(null);

  // Draggable divider between Sources and Recent Chats sections
  const sidebarRef = useRef(null);
  const dragCleanupRef = useRef(null);
  const messagesEndRef = useRef(null);
  // Holds the AbortController for the in-flight /chat/stream or /chat/resume
  // fetch, so the Stop button can cancel it. Aborting closes the SSE
  // connection; the backend's `aclosing(...)` around the LangGraph stream
  // (chat/router.py::_stream_agent_events) flushes the last checkpoint on
  // that disconnect, so the partial turn doesn't corrupt resumed state.
  const streamControllerRef = useRef(null);
  // Set right before a messages update that shouldn't jump the view to the
  // bottom (e.g. toggling a reasoning trace open/closed) -- consumed once by
  // the auto-scroll effect below, then reset.
  const skipAutoScrollRef = useRef(false);
  const [sourcesHeightPct, setSourcesHeightPct] = useState(45);

  useEffect(() => {
    return () => dragCleanupRef.current?.();
  }, []);

  function handleResizerMouseDown(event) {
    event.preventDefault();
    const handleMove = (moveEvent) => {
      if (!sidebarRef.current) return;
      const rect = sidebarRef.current.getBoundingClientRect();
      const pct = ((moveEvent.clientY - rect.top) / rect.height) * 100;
      setSourcesHeightPct(Math.min(80, Math.max(15, pct)));
    };
    const handleUp = () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      dragCleanupRef.current = null;
    };
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    dragCleanupRef.current = handleUp;
  }

  // Load session list on mount
  async function loadSessions() {
    setHistoryLoading(true);
    try {
      const sessions = await getChatSessions();
      setHistorySessions(Array.isArray(sessions) ? sessions : []);
    } catch {
      // Non-fatal: history panel just stays empty
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    loadSessions();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const groups = await getChatModels();
        setModelGroups(Array.isArray(groups) ? groups : []);
      } catch {
        // Non-fatal: fall back to the workspace default model.
      }
    })();
  }, []);

  // Load a prior session when navigated here with a sessionId in router state
  useEffect(() => {
    if (!resumeSessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const detail = await getChatSession(resumeSessionId);
        if (cancelled) return;
        restoreSession(detail);
      } catch {
        // Non-fatal
      }
    })();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumeSessionId]);

  // Sync selected docs when contextSourceIds changes externally
  useEffect(() => {
    setSelected((current) => {
      const stillSelected = current.filter((id) => contextSourceIds.includes(id));
      const newSources = contextSourceIds.filter((id) => !current.includes(id));
      return [...stillSelected, ...newSources];
    });
  }, [contextSourceIds]);

  useEffect(() => {
    if (skipAutoScrollRef.current) {
      skipAutoScrollRef.current = false;
      return;
    }
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    if (!citationDrawer.open) return;
    const targetId = `citation-card-${citationDrawer.focusIndex + 1}`;
    requestAnimationFrame(() => {
      document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }, [citationDrawer.open, citationDrawer.focusIndex]);

  // Claude-Code-style quick select: press a number key to pick that option of
  // the pending ask_user/confirm_import prompt. Escape only declines in
  // "confirm" mode (a clear yes/no gate) -- "choice"/"freeform" have no
  // universal "No" to fall back to. Ignored while typing in the prompt's own
  // text input (freeform question or the "Other" answer box).
  useEffect(() => {
    if (!pendingConfirm || confirmBusy) return undefined;
    const isImport = pendingConfirm.type === "confirm_import";
    const mode = isImport ? "confirm" : pendingConfirm.mode || "confirm";
    const options = isImport
      ? [true, false]
      : mode === "confirm"
        ? pendingConfirm.options || ["Yes", "No"]
        : pendingConfirm.options || [];

    function onKeyDown(event) {
      const tag = event.target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (event.key === "Escape") {
        if (mode === "confirm") handleConfirmResponse(isImport ? false : "No");
        return;
      }
      const index = Number(event.key) - 1;
      if (Number.isInteger(index) && index >= 0 && index < options.length) {
        handleConfirmResponse(options[index]);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [pendingConfirm, confirmBusy]);

  if (!user) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "flex-start", pt: 8 }}>
        <Card sx={{ p: 4, maxWidth: 420, width: "100%", textAlign: "center" }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Authentication required
          </Typography>
          <Typography variant="h2" sx={{ fontSize: 24, mb: 2 }}>
            Sign in to use Chat
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary", mb: 3 }}>
            The Q&amp;A chat is only available to registered users. Please log in or create an
            account to continue.
          </Typography>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
            <Button variant="contained" onClick={() => onNavigate("auth")}>
              Log in
            </Button>
            <Button variant="outlined" onClick={() => onNavigate("library")}>
              Browse document library
            </Button>
          </Box>
        </Card>
      </Box>
    );
  }

  function restoreSession(detail) {
    setMessages(
      detail.messages.map((m) => ({
        role: m.role,
        content: m.content,
        citations: Array.isArray(m.citations) ? m.citations : [],
        evidenceSufficient: m.evidence_sufficient,
        evidenceReason: null,
        responseMode: m.response_mode,
        answerMode: m.answer_mode,
        agentMode: m.agent_mode,
        model: m.model,
        // Historical trace steps carry the same shape consumeAgentStream
        // builds live, minus `label` (recomputed here since it's derived
        // purely from the tool name).
        steps: Array.isArray(m.steps)
          ? m.steps.map((s) => ({ ...s, label: TOOL_STATUS_LABEL[s.tool] || s.tool }))
          : [],
      })),
    );
    setSessionId(String(detail.id));
    if (detail.response_mode) setResponseMode(detail.response_mode);
    if (detail.response_mode === "policymaker") {
      setAnswerMode("analysis");
    } else {
      const lastAssistant = [...detail.messages].reverse().find((m) => m.role === "assistant");
      if (lastAssistant?.answer_mode) setAnswerMode(lastAssistant.answer_mode);
    }

    // Cross-reference stored document_ids against currently available documents
    const sessionDocIds = detail.document_ids || [];
    const found = [];
    const missing = [];
    for (const docId of sessionDocIds) {
      if (documents.some((d) => d.id === docId)) {
        found.push(docId);
      } else {
        missing.push(docId);
      }
    }
    if (onSetSources) onSetSources(found);
    if (missing.length > 0) {
      const noun = missing.length === 1 ? "document" : "documents";
      setSnackbar({
        open: true,
        message: `${missing.length} ${noun} from this session could not be found and may have been deleted.`,
      });
    }
  }

  async function handleLoadSession(id) {
    try {
      const detail = await getChatSession(id);
      restoreSession(detail);
    } catch {
      setError("Failed to load session.");
    }
  }

  function handleNewChat() {
    setMessages([]);
    setSessionId(null);
    setError("");
  }

  function handleExportMessage(message, index) {
    const questionMsg = index > 0 ? messages[index - 1] : null;
    const lines = [
      "AI Policy Assistant — Answer Export",
      `Exported: ${new Date().toLocaleString()}`,
      "",
    ];
    if (questionMsg) {
      lines.push(`Question: ${questionMsg.content}`);
      lines.push("");
    }
    lines.push("─".repeat(60));
    lines.push("");
    lines.push(message.content);
    if (message.citations?.length > 0) {
      lines.push("");
      lines.push("─".repeat(60));
      lines.push("Sources:");
      message.citations.forEach((c, i) => {
        lines.push(`[${i + 1}] ${c.title}${c.page ? `, p.${c.page}` : ""}`);
        if (c.quote) {
          const preview = c.quote.length > 200 ? `${c.quote.slice(0, 200)}...` : c.quote;
          lines.push(`    "${preview}"`);
        }
      });
    }
    const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `policy-answer-${Date.now()}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async function handleDeleteSession() {
    const id = deleteDialog.sessionId;
    setDeleteDialog({ open: false, sessionId: null });
    try {
      await deleteChatSession(id);
      if (sessionId === id) handleNewChat();
      setHistorySessions((prev) => prev.filter((s) => String(s.id) !== String(id)));
    } catch {
      setSnackbar({ open: true, message: "Failed to delete session." });
    }
  }

  async function handleRenameSession() {
    const { sessionId: id, title } = renameDialog;
    if (!title.trim()) return;
    setRenameDialog({ open: false, sessionId: null, title: "" });
    try {
      await renameChatSession(id, title.trim());
      setHistorySessions((prev) =>
        prev.map((s) => (String(s.id) === String(id) ? { ...s, title: title.trim() } : s)),
      );
    } catch {
      setSnackbar({ open: true, message: "Failed to rename session." });
    }
  }

  function drawerCitations(citations) {
    if (!citations || citations.length === 0) return [];
    return citations.map((c, i) => ({ ...c, _displayIndex: i + 1 }));
  }

  const sourceDocs = documents.filter((doc) => contextSourceIds.includes(doc.id));

  function toggleDocument(documentId) {
    setSelected((current) =>
      current.includes(documentId)
        ? current.filter((id) => id !== documentId)
        : [...current, documentId],
    );
  }

  function openCitationDrawer(citations, focusIndex = 0, evidenceSufficient = true, evidenceReason = null) {
    setCitationDrawer({ open: true, citations: citations || [], focusIndex, evidenceSufficient: evidenceSufficient !== false, evidenceReason: evidenceReason || null });
  }

  async function handleShowDocumentDetail(document) {
    setError("");
    // Open the drawer immediately with a skeleton; metadata and chunks both
    // fill in afterwards once their fetches resolve. `detailDrawerOpen` is a
    // single dedicated flag set once here and only cleared by
    // closeDocumentDetail(), so the drawer never flickers shut while
    // `detailDoc`/`detailLoading` are updating in between.
    setDetailDoc(null);
    setDetailChunks(null);
    setOpenChunkId(null);
    setDetailLoading(true);
    setDetailDrawerOpen(true);

    let detail;
    try {
      detail = await getDocumentDetail(document.id);
    } catch (detailError) {
      setError(detailError.message);
      setDetailLoading(false);
      return;
    }

    setDetailDoc(detail);
    setDetailLoading(false);

    if (document.status === "ready") {
      setDetailChunksLoading(true);
      try {
        setDetailChunks(await getDocumentChunks(document.id));
      } catch (chunkError) {
        setError(chunkError.message);
      } finally {
        setDetailChunksLoading(false);
      }
    }
  }

  function closeDocumentDetail() {
    setDetailDrawerOpen(false);
    setDetailDoc(null);
    setDetailLoading(false);
    setDetailChunks(null);
    setDetailChunksLoading(false);
    setOpenChunkId(null);
  }

  // Status text shown in the streaming placeholder while a tool runs, keyed
  // by tool name -- purely cosmetic, doesn't affect the answer.
  const TOOL_STATUS_LABEL = {
    search_internal_documents: "Searching the selected documents…",
    search_full_corpus: "Searching the full document library…",
    search_web: "Searching the web…",
    import_web_page: "Importing the page…",
    prepare_final_answer: "Preparing the final answer…",
  };

  function ensureStreamingPlaceholder(current) {
    const last = current[current.length - 1];
    if (last?.role === "assistant" && last.streaming) return [...current];
    return [
      ...current,
      { role: "assistant", content: "", streaming: true, responseMode, answerMode, agentMode, steps: [], showSteps: true },
    ];
  }

  // Shared by handleSubmit (new turn) and handleConfirmResponse (resumed
  // turn) -- both drive the same agent SSE event shapes onto the same
  // streaming assistant message. Returns true if the stream paused on a
  // confirm_* interrupt event, false if it ran to completion ("done").
  async function consumeAgentStream(streamGenerator) {
    for await (const evt of streamGenerator) {
      if (evt.type === "tool_call") {
        setMessages((current) => {
          const next = ensureStreamingPlaceholder(current);
          const last = next[next.length - 1];
          const steps = [
            ...(last.steps || []),
            {
              tool: evt.tool,
              label: TOOL_STATUS_LABEL[evt.tool] || evt.tool,
              status: "running",
              query: evt.query || null,
              decisionReason: evt.decision_reason || null,
              question: evt.question || null,
              url: evt.url || null,
              title: evt.title || null,
            },
          ];
          next[next.length - 1] = { ...last, steps, showSteps: true };
          return next;
        });
      } else if (evt.type === "tool_result") {
        setMessages((current) => {
          const last = current[current.length - 1];
          if (!last?.steps?.length) return current;
          const steps = [...last.steps];
          for (let i = steps.length - 1; i >= 0; i -= 1) {
            if (steps[i].tool === evt.tool && steps[i].status === "running") {
              steps[i] = {
                ...steps[i],
                status: "done",
                evidenceSufficient: evt.evidence_sufficient,
                evidenceReason: evt.evidence_reason || null,
                resultCount: Number.isInteger(evt.result_count) ? evt.result_count : null,
                sourceTitles: Array.isArray(evt.source_titles) ? evt.source_titles : [],
                answerPlan: evt.answer_plan || null,
                citationNumbers: Array.isArray(evt.citation_numbers) ? evt.citation_numbers : [],
              };
              break;
            }
          }
          const next = [...current];
          next[next.length - 1] = { ...last, steps };
          return next;
        });
      } else if (evt.type === "token") {
        setMessages((current) => {
          const next = ensureStreamingPlaceholder(current);
          const last = next[next.length - 1];
          const isFirstToken = !last.content;
          next[next.length - 1] = {
            ...last,
            content: last.content + evt.value,
            // Auto-collapse the reasoning trace the moment the real answer
            // starts arriving (GPT-style) -- but only once, so a user who
            // re-expands it while more tokens stream in isn't fought.
            showSteps: isFirstToken ? false : last.showSteps,
          };
          return next;
        });
      } else if (evt.type === "ask_user" || evt.type === "confirm_import") {
        setPendingConfirm(evt);
        return true;
      } else if (evt.type === "citations") {
        setMessages((current) => {
          const next = [...current];
          const last = next[next.length - 1];
          next[next.length - 1] = {
            ...last,
            citations: Array.isArray(evt.data) ? evt.data : [],
            evidenceSufficient: evt.evidence_sufficient,
            evidenceReason: evt.evidence_reason || null,
            responseMode: evt.response_mode || responseMode,
            answerMode: evt.answer_mode || answerMode,
            agentMode: evt.agent_mode || last.agentMode || agentMode,
            model: evt.model || null,
          };
          return next;
        });
        if (evt.session_id && !sessionId) {
          setSessionId(String(evt.session_id));
          loadSessions();
        }
      } else if (evt.type === "error") {
        throw new Error(evt.message);
      } else if (evt.type === "done") {
        setMessages((current) => {
          const next = [...current];
          const last = next[next.length - 1];
          if (!last?.streaming) return current;
          next[next.length - 1] = { ...last, streaming: false };
          return next;
        });
      }
    }
    return false;
  }

  function handleStop() {
    streamControllerRef.current?.abort();
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const cleanQuestion = question.trim();
    if (!cleanQuestion || !selected.length || busy) return;

    setMessages((current) => [...current, { role: "user", content: cleanQuestion }]);
    setQuestion("");
    setBusy(true);
    setError("");

    const controller = new AbortController();
    streamControllerRef.current = controller;

    let paused = false;
    try {
      paused = await consumeAgentStream(
        askQuestionStream(
          cleanQuestion, selected, responseMode, answerMode, messages, sessionId, selectedModel,
          controller.signal, agentMode,
        ),
      );
    } catch (chatError) {
      if (chatError.name !== "AbortError") {
        setError(chatError.message);
        setMessages((current) => current.filter((m) => !m.streaming));
      }
    } finally {
      streamControllerRef.current = null;
      setBusy(false);
      // Clear streaming flag if the connection closed before a "done" event
      // arrived (including a user-initiated stop) and we're not waiting on
      // a confirm_* dialog. Keeps whatever partial content already streamed.
      setMessages((current) => {
        const last = current[current.length - 1];
        if (!last?.streaming || paused) return current;
        const next = [...current];
        next[next.length - 1] = { ...last, streaming: false };
        return next;
      });
    }
  }

  async function handleConfirmResponse(answer) {
    if (!pendingConfirm) return;
    const { session_id: confirmSessionId } = pendingConfirm;
    setPendingConfirm(null);
    setConfirmBusy(true);
    setBusy(true);

    const controller = new AbortController();
    streamControllerRef.current = controller;

    let paused = false;
    try {
      paused = await consumeAgentStream(resumeChatStream(confirmSessionId, answer, controller.signal));
    } catch (chatError) {
      if (chatError.name !== "AbortError") {
        setError(chatError.message);
        setMessages((current) => current.filter((m) => !m.streaming));
      }
    } finally {
      streamControllerRef.current = null;
      setConfirmBusy(false);
      setBusy(false);
      setMessages((current) => {
        const last = current[current.length - 1];
        if (!last?.streaming || paused) return current;
        const next = [...current];
        next[next.length - 1] = { ...last, streaming: false };
        return next;
      });
    }
  }

  function toggleSteps(messageIndex) {
    skipAutoScrollRef.current = true;
    setMessages((current) => {
      const target = current[messageIndex];
      if (!target) return current;
      const next = [...current];
      next[messageIndex] = { ...target, showSteps: !target.showSteps };
      return next;
    });
  }

  function handleQuestionKeyDown(event) {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  async function handleOpenCitation(citation) {
    setError("");
    try {
      await openDocumentFile(citation.document_id, citation.page);
    } catch (sourceError) {
      setError(sourceError.message);
    }
  }

  return (
    <Box component="section" sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <Box sx={{ flex: 1, minHeight: 0, display: "flex", gap: 2, flexDirection: { xs: "column", md: "row" }, alignItems: "stretch" }}>

        {/* Left panel: Sources (top) + History (bottom), height split is user-resizable */}
        <Box
          ref={sidebarRef}
          sx={{
            width: { xs: "100%", md: 280 },
            flexShrink: 0,
            display: "flex",
            flexDirection: "column",
            height: "100%",
          }}
        >
          {/* ── Sources section ── */}
          <Card
            sx={{
              height: `${sourcesHeightPct}%`,
              flexShrink: 0,
              p: 0,
              px: 3,
              pt: 3,
              pb: 1.5,
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
          >
            <Typography variant="subtitle2" sx={{ flexShrink: 0 }}>Context</Typography>
            <Typography variant="h2" sx={{ fontSize: 22, mb: 1.5, flexShrink: 0 }}>Sources</Typography>
            {sourceDocs.length === 0 ? (
              <Box sx={{ py: 2, textAlign: "center" }}>
                <Typography variant="body2" sx={{ color: "text.secondary", mb: 1.5 }}>
                  No source files added yet.
                </Typography>
                <Button variant="outlined" size="small" onClick={() => onNavigate("library")}>
                  Find files
                </Button>
              </Box>
            ) : (
              <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
                {sourceDocs.map((document) => (
                  <Box
                    key={document.id || document.name}
                    sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}
                  >
                    <Box sx={{ display: "flex", alignItems: "center", flex: 1, minWidth: 0 }}>
                      <Checkbox
                        checked={selected.includes(document.id)}
                        onChange={() => toggleDocument(document.id)}
                        size="small"
                      />
                      <Typography
                        variant="body2"
                        onClick={() => handleShowDocumentDetail(document)}
                        title="View document details"
                        sx={{
                          wordBreak: "break-word",
                          fontSize: 13,
                          cursor: "pointer",
                          "&:hover": { textDecoration: "underline", color: "#214f42" },
                        }}
                      >
                        {document.title || document.name}
                      </Typography>
                    </Box>
                    <IconButton
                      size="small"
                      title="Remove from context"
                      onClick={() => onRemoveSource(document.id)}
                      sx={{ color: "#bbb" }}
                    >
                      <CloseIcon sx={{ fontSize: 14 }} />
                    </IconButton>
                  </Box>
                ))}
              </Box>
            )}
            {sourceDocs.length > 0 && (
              <Button
                size="small"
                variant="text"
                onClick={() => onNavigate("library")}
                sx={{ mt: 0.5, flexShrink: 0, fontSize: "0.75em", color: "#214f42", textTransform: "none", px: 0 }}
              >
                + Add more sources
              </Button>
            )}
          </Card>

          {/* ── Draggable handle — resizes Sources vs. Recent Chats ── */}
          <Box
            onMouseDown={handleResizerMouseDown}
            sx={{
              flexShrink: 0,
              height: 16,
              cursor: "row-resize",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              "&:hover .resize-handle-grip": { bgcolor: "#9db3a7" },
            }}
          >
            <Box
              className="resize-handle-grip"
              sx={{ width: 40, height: 4, borderRadius: 999, bgcolor: "#c8d0cb", transition: "background-color 0.15s" }}
            />
          </Box>

          {/* ── History section ── */}
          <Card sx={{ flex: 1, minHeight: 0, p: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <Box
            sx={{
              px: 2,
              pt: 1.5,
              pb: 1,
              flexShrink: 0,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <Typography variant="subtitle2" sx={{ fontSize: 12, fontWeight: 700, color: "text.secondary", textTransform: "uppercase", letterSpacing: 0.5 }}>
              Recent Chats
            </Typography>
            <Tooltip title="New chat">
              <IconButton size="small" onClick={handleNewChat} sx={{ color: "#214f42" }}>
                <AddIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>

          <Box sx={{ flex: 1, overflowY: "auto", minHeight: 0, pb: 1 }}>
            {historyLoading && (
              <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
                <CircularProgress size={18} />
              </Box>
            )}
            {!historyLoading && historySessions.length === 0 && (
              <Typography variant="body2" sx={{ color: "text.secondary", textAlign: "center", py: 2, px: 2, fontSize: 12 }}>
                No previous chats
              </Typography>
            )}
            {historySessions.map((session) => {
              const isActive = String(session.id) === String(sessionId);
              return (
                <Box
                  key={session.id}
                  sx={{
                    position: "relative",
                    mx: 0.5,
                    mb: 0.25,
                    borderRadius: 1.5,
                    bgcolor: isActive ? "#e8f0ed" : "transparent",
                    "&:hover": { bgcolor: isActive ? "#e0ece7" : "#f5f5f0" },
                    "&:hover .session-actions": { opacity: 1 },
                  }}
                >
                  <ListItemButton
                    dense
                    onClick={() => handleLoadSession(String(session.id))}
                    sx={{ borderRadius: 1.5, pr: 7, py: 0.75 }}
                  >
                    <ListItemText
                      primary={
                        <Typography
                          variant="body2"
                          sx={{
                            fontSize: 13,
                            fontWeight: isActive ? 700 : 400,
                            overflow: "hidden",
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                            lineHeight: 1.35,
                          }}
                        >
                          {session.title}
                        </Typography>
                      }
                      secondary={
                        <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 11 }}>
                          {formatSessionDate(session.updated_at)}
                        </Typography>
                      }
                    />
                  </ListItemButton>
                  {/* Action icons — visible on hover */}
                  <Box
                    className="session-actions"
                    sx={{
                      position: "absolute",
                      right: 4,
                      top: "50%",
                      transform: "translateY(-50%)",
                      display: "flex",
                      gap: 0.25,
                      opacity: isActive ? 1 : 0,
                      transition: "opacity 0.15s",
                    }}
                  >
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        setRenameDialog({ open: true, sessionId: String(session.id), title: session.title });
                      }}
                      sx={{ color: "#888", p: 0.5 }}
                    >
                      <EditOutlinedIcon sx={{ fontSize: 14 }} />
                    </IconButton>
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteDialog({ open: true, sessionId: String(session.id) });
                      }}
                      sx={{ color: "#888", p: 0.5 }}
                    >
                      <DeleteOutlineIcon sx={{ fontSize: 14 }} />
                    </IconButton>
                  </Box>
                </Box>
              );
            })}
          </Box>
          </Card>
        </Box>

        {/* Chat Panel */}
        <Card sx={{ p: 3, flex: 1, minWidth: 0, height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <Box
            sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: "20px", flexShrink: 0 }}
          >
            <Box>
              <Typography variant="subtitle2">Conversation</Typography>
              <Typography variant="h2" sx={{ fontSize: 24 }}>Chat</Typography>
            </Box>
            <Button variant="outlined" onClick={handleNewChat}>
              New Chat
            </Button>
          </Box>

          {/* Messages */}
          <Box sx={{ mb: 3, flex: 1, minHeight: 0, overflowY: "auto" }}>
            {messages.length === 0 && (
              <Typography sx={{ py: 4, textAlign: "center", color: "text.secondary" }}>
                Ask a question to start a conversation.
              </Typography>
            )}
            {messages.map((message, index) => {
              const isLowEvidence = message.evidenceSufficient === false;
              const isChatMode = message.answerMode === "chat";
              return (
                <Box
                  key={`${message.role}-${index}`}
                  sx={{
                    mb: 2,
                    p: 2,
                    borderRadius: 2,
                    bgcolor: message.role === "user" ? "#f0f5f2" : "#fff",
                    border: "1px solid",
                    borderColor: isLowEvidence ? "#ffcdd2" : "#e2e5df",
                  }}
                >
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                    <Typography variant="body2" sx={{ fontWeight: 800 }}>
                      {message.role === "user" ? "You" : "Assistant"}
                    </Typography>
                    {message.role === "assistant" && (message.responseMode || message.answerMode) && (
                      <Typography component="small" variant="caption" sx={{ color: "text.secondary" }}>
                        {[
                          getResponseModeLabel(message.responseMode || "researcher"),
                          message.answerMode === "chat" ? "Open Discussion" : "Document Analysis",
                          message.agentMode === "direct" ? "Direct" : null,
                          message.model ? `Answered by ${getModelLabel(modelLabels, message.model)}` : null,
                        ].filter(Boolean).join(" · ")}
                      </Typography>
                    )}
                    {message.role === "assistant" && (
                      <Box sx={{ ml: "auto", display: "flex", alignItems: "center", gap: 0.5 }}>
                        {message.citations?.length > 0 && (
                          <Button
                            size="small"
                            variant="text"
                            onClick={() => openCitationDrawer(message.citations, 0, message.evidenceSufficient, message.evidenceReason)}
                            sx={{
                              fontSize: "0.72em",
                              color: isLowEvidence ? "#d84315" : "#214f42",
                              textTransform: "none",
                              minWidth: 0,
                              px: 1,
                              py: 0,
                            }}
                          >
                            {isLowEvidence && "⚠ "}
                            {message.citations.length} source{message.citations.length !== 1 ? "s" : ""}
                          </Button>
                        )}
                        <Tooltip title={copiedIdx === index ? "Copied!" : "Copy"}>
                          <IconButton
                            size="small"
                            onClick={() => {
                              navigator.clipboard.writeText(message.content);
                              setCopiedIdx(index);
                              setTimeout(() => setCopiedIdx((prev) => (prev === index ? null : prev)), 2000);
                            }}
                            sx={{ color: "#888", p: 0.5 }}
                          >
                            <ContentCopyIcon sx={{ fontSize: 14 }} />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Export answer">
                          <IconButton
                            size="small"
                            onClick={() => handleExportMessage(message, index)}
                            sx={{ color: "#888", p: 0.5 }}
                          >
                            <FileDownloadOutlinedIcon sx={{ fontSize: 14 }} />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    )}
                  </Box>

                  {/* Low evidence banner — analysis mode: error (answer was withheld) */}
                  {message.role === "assistant" && isLowEvidence && !isChatMode && (
                    <Alert severity="error" sx={{ mb: 1.5, py: 0.75, fontSize: 13 }}>
                      <strong>Insufficient Evidence</strong> — The selected documents do not contain passages closely related to this question. The answer has been withheld to avoid hallucination.
                    </Alert>
                  )}

                  {/* Low evidence banner — chat mode: warning (answer produced but weak) */}
                  {message.role === "assistant" && isLowEvidence && isChatMode && (
                    <Alert severity="warning" sx={{ mb: 1.5, py: 0.75, fontSize: 13 }}>
                      <strong>Low-confidence answer</strong> — The selected documents contain limited relevant evidence. This response may draw on general knowledge beyond the provided documents.
                    </Alert>
                  )}

                  {message.role === "assistant" ? (
                    <Box
                      sx={{
                        fontSize: "14px",
                        lineHeight: 1.7,
                        "& h1, & h2, & h3": { fontFamily: "Georgia, serif", mt: 2, mb: 1, lineHeight: 1.2 },
                        "& h1": { fontSize: "1.4em" },
                        "& h2": { fontSize: "1.2em" },
                        "& h3": { fontSize: "1.05em" },
                        "& p": { my: 0.75 },
                        "& ul, & ol": { pl: 2.5, my: 0.75 },
                        "& li": { mb: 0.25 },
                        "& code": {
                          px: 0.75, py: 0.25, borderRadius: 1,
                          bgcolor: "#f0f3ed", fontSize: "0.9em", fontFamily: "monospace",
                        },
                        "& pre": {
                          p: 2, borderRadius: 2, bgcolor: "#f5f5f0", overflow: "auto", fontSize: "0.85em",
                          "& code": { p: 0, bgcolor: "transparent" },
                        },
                        "& blockquote": { mx: 0, px: 2, borderLeft: "3px solid #214f42", color: "#63706a" },
                        "& table": { borderCollapse: "collapse", width: "100%", my: 1 },
                        "& th, & td": { border: "1px solid #d9d8d0", px: 1.5, py: 1, textAlign: "left" },
                        "& th": { bgcolor: "#f5f5f0", fontWeight: 800 },
                        "& a": { color: "#214f42" },
                      }}
                    >
                      {message.role === "assistant" && (
                        <ReasoningSteps
                          steps={message.steps}
                          expanded={Boolean(message.showSteps)}
                          onToggle={() => toggleSteps(index)}
                          active={Boolean(message.streaming) && !message.content}
                        />
                      )}
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={makeMarkdownComponents(
                          message.citations || [],
                          (cits, idx) => openCitationDrawer(cits, idx, message.evidenceSufficient, message.evidenceReason),
                          isLowEvidence,
                        )}
                      >
                        {message.content}
                      </ReactMarkdown>
                      {message.streaming && (
                        <Box
                          component="span"
                          sx={{
                            display: "inline-block",
                            width: "2px",
                            height: "0.9em",
                            bgcolor: "#214f42",
                            ml: "2px",
                            verticalAlign: "text-bottom",
                            animation: "blink 1s step-end infinite",
                            "@keyframes blink": { "0%,100%": { opacity: 1 }, "50%": { opacity: 0 } },
                          }}
                        />
                      )}
                    </Box>
                  ) : (
                    <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                      {message.content}
                    </Typography>
                  )}

                  {/* CitationList only appears for low-evidence chat-mode responses */}
                  {message.role === "assistant" && isLowEvidence && isChatMode && message.citations?.length > 0 && (
                    <CitationList
                      citations={message.citations}
                      onOpenSource={handleOpenCitation}
                      lowEvidence={true}
                    />
                  )}

                  {message.truncated && (
                    <Typography variant="caption" sx={{ color: "warning.main" }}>
                      The combined PDF text was truncated.
                    </Typography>
                  )}
                </Box>
              );
            })}
            <ConfirmPrompt confirm={pendingConfirm} busy={confirmBusy} onAnswer={handleConfirmResponse} />
            {busy && !messages[messages.length - 1]?.streaming && (
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, p: 2 }}>
                <Box sx={{ display: "flex", gap: "4px", alignItems: "center" }}>
                  {[0, 1, 2].map((i) => (
                    <Box
                      key={i}
                      sx={{
                        width: 7,
                        height: 7,
                        borderRadius: "50%",
                        bgcolor: "#214f42",
                        animation: "bounce 1.2s ease-in-out infinite",
                        animationDelay: `${i * 0.2}s`,
                        "@keyframes bounce": {
                          "0%, 80%, 100%": { transform: "scale(0.6)", opacity: 0.4 },
                          "40%": { transform: "scale(1)", opacity: 1 },
                        },
                      }}
                    />
                  ))}
                </Box>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Searching documents...
                </Typography>
              </Box>
            )}
            <div ref={messagesEndRef} />
          </Box>

          {error && <Alert severity="error" sx={{ mb: 2, flexShrink: 0 }}>{error}</Alert>}

          {/* Mode selectors */}
          <Box sx={{ mb: 2, flexShrink: 0, display: "flex", flexWrap: "wrap", gap: 1.5, alignItems: "center" }}>
            <Box>
              <Button
                variant="outlined"
                size="small"
                disabled={busy}
                onClick={(event) => setResponseModeAnchor(event.currentTarget)}
                aria-haspopup="menu"
                sx={{
                  flexDirection: "column",
                  alignItems: "flex-start",
                  py: 0.75,
                  px: 1.25,
                  gap: 0,
                  minWidth: 0,
                  textTransform: "none",
                }}
              >
                <Typography component="span" sx={{ fontSize: "0.68rem", color: "text.secondary", lineHeight: 1, display: "block" }}>
                  Writing style
                </Typography>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.25, mt: 0.25 }}>
                  <Typography component="span" sx={{ fontSize: "0.8125rem", fontWeight: 600, lineHeight: 1 }}>
                    {getOptionLabel(RESPONSE_MODE_OPTIONS, responseMode)}
                  </Typography>
                  <ArrowDropDownIcon sx={{ fontSize: 16, color: "text.secondary", ml: 0.25 }} />
                </Box>
              </Button>
              <Menu
                anchorEl={responseModeAnchor}
                open={Boolean(responseModeAnchor)}
                onClose={() => setResponseModeAnchor(null)}
                anchorOrigin={{ vertical: "top", horizontal: "left" }}
                transformOrigin={{ vertical: "bottom", horizontal: "left" }}
              >
                {RESPONSE_MODE_OPTIONS.map((option) => (
                  <MenuItem
                    key={option.value}
                    selected={option.value === responseMode}
                    onClick={() => {
                      setResponseMode(option.value);
                      if (option.value === "policymaker") setAnswerMode("analysis");
                      setResponseModeAnchor(null);
                    }}
                  >
                    <ListItemText primary={option.label} secondary={option.description} />
                  </MenuItem>
                ))}
              </Menu>
            </Box>

            <Box>
              <Button
                variant="outlined"
                size="small"
                disabled={busy || responseMode === "policymaker"}
                onClick={(event) => setAnswerModeAnchor(event.currentTarget)}
                aria-haspopup="menu"
                sx={{
                  flexDirection: "column",
                  alignItems: "flex-start",
                  py: 0.75,
                  px: 1.25,
                  gap: 0,
                  minWidth: 0,
                  textTransform: "none",
                }}
              >
                <Typography component="span" sx={{ fontSize: "0.68rem", color: "text.secondary", lineHeight: 1, display: "block" }}>
                  Answer purpose
                </Typography>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.25, mt: 0.25 }}>
                  <Typography component="span" sx={{ fontSize: "0.8125rem", fontWeight: 600, lineHeight: 1 }}>
                    {getOptionLabel(ANSWER_MODE_OPTIONS, answerMode)}
                  </Typography>
                  <ArrowDropDownIcon sx={{ fontSize: 16, color: "text.secondary", ml: 0.25 }} />
                </Box>
              </Button>
              <Menu
                anchorEl={answerModeAnchor}
                open={Boolean(answerModeAnchor)}
                onClose={() => setAnswerModeAnchor(null)}
                anchorOrigin={{ vertical: "top", horizontal: "left" }}
                transformOrigin={{ vertical: "bottom", horizontal: "left" }}
              >
                {ANSWER_MODE_OPTIONS
                  .filter((option) => responseMode !== "policymaker" || option.value === "analysis")
                  .map((option) => (
                  <MenuItem
                    key={option.value}
                    selected={option.value === answerMode}
                    onClick={() => { setAnswerMode(option.value); setAnswerModeAnchor(null); }}
                  >
                    <ListItemText primary={option.label} secondary={option.description} />
                  </MenuItem>
                ))}
              </Menu>
            </Box>

            <Box>
              <Button
                variant="outlined"
                size="small"
                disabled={busy}
                onClick={(event) => setAgentModeAnchor(event.currentTarget)}
                aria-haspopup="menu"
                sx={{
                  flexDirection: "column",
                  alignItems: "flex-start",
                  py: 0.75,
                  px: 1.25,
                  gap: 0,
                  minWidth: 0,
                  textTransform: "none",
                }}
              >
                <Typography component="span" sx={{ fontSize: "0.68rem", color: "text.secondary", lineHeight: 1, display: "block" }}>
                  Reasoning mode
                </Typography>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.25, mt: 0.25 }}>
                  <Typography component="span" sx={{ fontSize: "0.8125rem", fontWeight: 600, lineHeight: 1 }}>
                    {getOptionLabel(AGENT_MODE_OPTIONS, agentMode)}
                  </Typography>
                  <ArrowDropDownIcon sx={{ fontSize: 16, color: "text.secondary", ml: 0.25 }} />
                </Box>
              </Button>
              <Menu
                anchorEl={agentModeAnchor}
                open={Boolean(agentModeAnchor)}
                onClose={() => setAgentModeAnchor(null)}
                anchorOrigin={{ vertical: "top", horizontal: "left" }}
                transformOrigin={{ vertical: "bottom", horizontal: "left" }}
              >
                {AGENT_MODE_OPTIONS.map((option) => (
                  <MenuItem
                    key={option.value}
                    selected={option.value === agentMode}
                    onClick={() => { setAgentMode(option.value); setAgentModeAnchor(null); }}
                  >
                    <ListItemText primary={option.label} secondary={option.description} />
                  </MenuItem>
                ))}
              </Menu>
            </Box>

            {modelGroups.length > 0 && (
              <Box>
                <Button
                  variant="outlined"
                  size="small"
                  disabled={busy}
                  onClick={(event) => setModelAnchor(event.currentTarget)}
                  aria-haspopup="menu"
                  sx={{
                    flexDirection: "column",
                    alignItems: "flex-start",
                    py: 0.75,
                    px: 1.25,
                    gap: 0,
                    minWidth: 0,
                    textTransform: "none",
                  }}
                >
                  <Typography component="span" sx={{ fontSize: "0.68rem", color: "text.secondary", lineHeight: 1, display: "block" }}>
                    Model
                  </Typography>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.25, mt: 0.25 }}>
                    <Typography component="span" sx={{ fontSize: "0.8125rem", fontWeight: 600, lineHeight: 1 }}>
                      {selectedModel ? getModelLabel(modelLabels, selectedModel) : "Workspace default"}
                    </Typography>
                    <ArrowDropDownIcon sx={{ fontSize: 16, color: "text.secondary", ml: 0.25 }} />
                  </Box>
                </Button>
                <Menu
                  anchorEl={modelAnchor}
                  open={Boolean(modelAnchor)}
                  onClose={() => setModelAnchor(null)}
                  anchorOrigin={{ vertical: "top", horizontal: "left" }}
                  transformOrigin={{ vertical: "bottom", horizontal: "left" }}
                >
                  <MenuItem
                    selected={!selectedModel}
                    onClick={() => { setSelectedModel(null); setModelAnchor(null); }}
                  >
                    <ListItemText primary="Workspace default" secondary="Use the admin-configured default model" />
                  </MenuItem>
                  {modelGroups.map((group) => [
                    <ListSubheader key={group.provider} sx={{ lineHeight: "32px" }}>
                      {group.provider_label}
                    </ListSubheader>,
                    ...group.models.map((option) => (
                      <MenuItem
                        key={option.id}
                        selected={option.id === selectedModel}
                        onClick={() => { setSelectedModel(option.id); setModelAnchor(null); }}
                      >
                        <ListItemText primary={option.label} />
                      </MenuItem>
                    )),
                  ])}
                </Menu>
              </Box>
            )}
          </Box>

          {/* Chat Form */}
          <Box component="form" onSubmit={handleSubmit} sx={{ display: "flex", gap: 1, flexShrink: 0 }}>
            <TextField
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={handleQuestionKeyDown}
              placeholder={
                selected.length
                  ? "Ask a question about the selected PDFs..."
                  : "Please select at least one document first..."
              }
              multiline
              rows={3}
              disabled={!selected.length}
              fullWidth
              size="small"
            />
            {busy ? (
              <Button
                variant="outlined"
                color="error"
                onClick={handleStop}
                sx={{ alignSelf: "flex-end", minWidth: 80 }}
                endIcon={<StopIcon />}
              >
                Stop
              </Button>
            ) : (
              <Button
                variant="contained"
                disabled={!question.trim() || !selected.length}
                type="submit"
                sx={{ alignSelf: "flex-end", minWidth: 80 }}
                endIcon={<SendIcon />}
              >
                Send
              </Button>
            )}
          </Box>
        </Card>
      </Box>

      {/* Citation Drawer */}
      <Drawer
        anchor="right"
        open={citationDrawer.open}
        onClose={() => setCitationDrawer((s) => ({ ...s, open: false }))}
        PaperProps={{
          sx: {
            width: { xs: "100%", sm: 440 },
            boxSizing: "border-box",
            display: "flex",
            flexDirection: "column",
            bgcolor: "#fafaf8",
          },
        }}
      >
        {/* Drawer header */}
        <Box
          sx={{
            px: 3,
            py: 2,
            bgcolor: citationDrawer.evidenceSufficient === false ? "#fff3e0" : "#fff",
            borderBottom: "1px solid",
            borderColor: citationDrawer.evidenceSufficient === false ? "#ffe0b2" : "#e2e5df",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexShrink: 0,
          }}
        >
          <Box>
            <Typography
              variant="h6"
              sx={{
                fontFamily: "Georgia, serif",
                fontSize: 18,
                lineHeight: 1.2,
                color: citationDrawer.evidenceSufficient === false ? "#bf360c" : "inherit",
              }}
            >
              {citationDrawer.evidenceSufficient === false ? "⚠ Sources (Low Confidence)" : "Sources"}
            </Typography>
            {citationDrawer.citations.length > 0 && (
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                {citationDrawer.citations.length} passage{citationDrawer.citations.length !== 1 ? "s" : ""} retrieved
              </Typography>
            )}
          </Box>
          <IconButton
            onClick={() => setCitationDrawer((s) => ({ ...s, open: false }))}
            size="small"
            sx={{ color: "#888" }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        {/* Low-evidence warning banner in drawer */}
        {citationDrawer.evidenceSufficient === false && (
          <Box
            sx={{
              px: 2.5,
              py: 1.5,
              bgcolor: "#fbe9e7",
              borderBottom: "1px solid #ffccbc",
              flexShrink: 0,
            }}
          >
            <Typography variant="body2" sx={{ fontSize: 12.5, color: "#bf360c", lineHeight: 1.6 }}>
              <strong>Evidence quality is low.</strong> The passages below were the closest matches found, but they may not be directly relevant to the question. Treat this answer with caution.
            </Typography>
          </Box>
        )}

        {/* Citations list */}
        <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
          {citationDrawer.citations.length === 0 ? (
            <Box sx={{ py: 6, textAlign: "center" }}>
              <Typography variant="body2" sx={{ color: "text.secondary" }}>
                No citation details available.
              </Typography>
            </Box>
          ) : (
            drawerCitations(citationDrawer.citations, citationDrawer.focusIndex).map((c, i) => {
              const isFocused = c._displayIndex === citationDrawer.focusIndex + 1;
              const isLow = citationDrawer.evidenceSufficient === false;
              const accentColor = isLow ? "#d84315" : "#214f42";
              const accentLight = isLow ? "#fbe9e7" : "#f0f7f4";
              const borderFocused = isLow ? "#d84315" : "#214f42";
              const badgeBg = isFocused ? accentColor : (isLow ? "#ffccbc" : "#e4ece9");
              const badgeColor = isFocused ? "#fff" : accentColor;
              return (
                <Box
                  key={i}
                  id={`citation-card-${c._displayIndex}`}
                  sx={{
                    mb: 2,
                    borderRadius: 2,
                    border: "1px solid",
                    borderColor: isFocused ? borderFocused : (isLow ? "#ffccbc" : "#dfe4de"),
                    bgcolor: "#fff",
                    overflow: "hidden",
                    boxShadow: isFocused ? `0 0 0 2px ${accentColor}22` : "none",
                    transition: "box-shadow 0.2s, border-color 0.2s",
                  }}
                >
                  {/* Card header: badge + title */}
                  <Box
                    sx={{
                      px: 2,
                      pt: 1.5,
                      pb: 1,
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 1.25,
                      bgcolor: isFocused ? accentLight : "#fff",
                    }}
                  >
                    <Box
                      sx={{
                        flexShrink: 0,
                        width: 26,
                        height: 26,
                        borderRadius: "50%",
                        bgcolor: badgeBg,
                        color: badgeColor,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontWeight: 800,
                        fontSize: 11,
                        mt: 0.1,
                      }}
                    >
                      {c._displayIndex}
                    </Box>
                    <Typography
                      variant="body2"
                      sx={{ fontWeight: 700, fontSize: 13, lineHeight: 1.4, flex: 1 }}
                    >
                      {c.title || "Unknown source"}
                    </Typography>
                  </Box>

                  {/* Page badge */}
                  {c.page != null && (
                    <Box sx={{ px: 2, pb: 1 }}>
                      <Box
                        component="span"
                        sx={{
                          display: "inline-block",
                          px: 0.75,
                          py: 0.15,
                          borderRadius: 1,
                          bgcolor: isLow ? "#ffccbc" : "#eef0ec",
                          fontSize: 11,
                          color: isLow ? "#bf360c" : "#4a5a54",
                          fontWeight: 600,
                        }}
                      >
                        Page {c.page}
                      </Box>
                    </Box>
                  )}

                  {/* Quote */}
                  {c.quote && (
                    <Box
                      sx={{
                        mx: 2,
                        mb: 1.5,
                        px: 1.5,
                        py: 1,
                        borderLeft: `3px solid ${isLow ? "#ff8a65" : "#c8d9d4"}`,
                        bgcolor: isLow ? "#fff8f5" : "#f8fbf9",
                        borderRadius: "0 4px 4px 0",
                      }}
                    >
                      <Typography
                        variant="body2"
                        sx={{
                          fontSize: 12.5,
                          lineHeight: 1.7,
                          color: isLow ? "#5d2b1e" : "#4a5a54",
                          fontStyle: "italic",
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-word",
                        }}
                      >
                        &ldquo;{c.quote.length > 400 ? c.quote.slice(0, 400) + "…" : c.quote}&rdquo;
                      </Typography>
                    </Box>
                  )}

                  {/* Open PDF action */}
                  {c.document_id && (
                    <Box sx={{ px: 2, pb: 1.5 }}>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={async () => {
                          try {
                            await openDocumentFile(c.document_id, c.page);
                          } catch {
                            setError("Could not open the source document.");
                          }
                        }}
                        sx={{
                          fontSize: 11,
                          textTransform: "none",
                          borderColor: isLow ? "#ffab91" : "#c8d9d4",
                          color: accentColor,
                          py: 0.4,
                          px: 1.25,
                          "&:hover": { borderColor: accentColor, bgcolor: accentLight },
                        }}
                      >
                        Open PDF{c.page != null ? ` at page ${c.page}` : ""}
                      </Button>
                    </Box>
                  )}
                  {!c.document_id && c.source_url && (
                    <Box sx={{ px: 2, pb: 1.5 }}>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => window.open(c.source_url, "_blank", "noopener,noreferrer")}
                        sx={{
                          fontSize: 11,
                          textTransform: "none",
                          borderColor: isLow ? "#ffab91" : "#c8d9d4",
                          color: accentColor,
                          py: 0.4,
                          px: 1.25,
                          "&:hover": { borderColor: accentColor, bgcolor: accentLight },
                        }}
                      >
                        Open web page
                      </Button>
                    </Box>
                  )}
                </Box>
              );
            })
          )}
        </Box>
      </Drawer>

      {/* Document detail drawer — opened from the Sources module */}
      <DocumentDrawer
        open={detailDrawerOpen}
        detail={detailDoc}
        detailLoading={detailLoading}
        chunks={detailChunks}
        chunksLoading={detailChunksLoading}
        openChunkId={openChunkId}
        onToggleChunk={(chunkId) => setOpenChunkId(openChunkId === chunkId ? null : chunkId)}
        onClose={closeDocumentDetail}
      />

      {/* Missing documents warning */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={7000}
        onClose={() => setSnackbar((s) => ({ ...s, open: false }))}
        message={snackbar.message}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />

      {/* Rename dialog */}
      <Dialog
        open={renameDialog.open}
        onClose={() => setRenameDialog({ open: false, sessionId: null, title: "" })}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Rename Chat</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            size="small"
            value={renameDialog.title}
            onChange={(e) => setRenameDialog((s) => ({ ...s, title: e.target.value }))}
            onKeyDown={(e) => { if (e.key === "Enter") handleRenameSession(); }}
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRenameDialog({ open: false, sessionId: null, title: "" })}>
            Cancel
          </Button>
          <Button variant="contained" onClick={handleRenameSession} disabled={!renameDialog.title.trim()}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete confirmation dialog */}
      <Dialog
        open={deleteDialog.open}
        onClose={() => setDeleteDialog({ open: false, sessionId: null })}
        maxWidth="xs"
      >
        <DialogTitle>Delete chat?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">This will permanently delete the session and all its messages.</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialog({ open: false, sessionId: null })}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleDeleteSession}>Delete</Button>
        </DialogActions>
      </Dialog>

    </Box>
  );
}
