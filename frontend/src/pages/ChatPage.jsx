import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControlLabel,
  IconButton,
  ListItemButton,
  ListItemText,
  Menu,
  MenuItem,
  Snackbar,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import ArrowDropDownIcon from "@mui/icons-material/ArrowDropDown";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/Delete";
import EditOutlinedIcon from "@mui/icons-material/Edit";
import SendIcon from "@mui/icons-material/Send";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  askQuestion,
  deleteChatSession,
  getChatSession,
  getChatSessions,
  openDocumentFile,
  renameChatSession,
} from "../api";
import CitationList from "../components/CitationList";

// Splits text on citation markers [1], [1-3], [1, 2] and wraps in clickable <sup>
const CITATION_RE = /(\[\d+(?:[-,]\s*\d+)*\])/;

function renderWithCitations(children, citations, onOpen) {
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
              color: "#214f42",
              fontWeight: 700,
              background: "none",
              border: "none",
              padding: "0 1px",
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

function makeMarkdownComponents(citations, onOpen) {
  return {
    p: ({ children }) => <p>{renderWithCitations(children, citations, onOpen)}</p>,
    li: ({ children }) => <li>{renderWithCitations(children, citations, onOpen)}</li>,
  };
}

const RESPONSE_MODE_OPTIONS = [
  {
    value: "researcher",
    label: "Policy Researcher",
    description: "Dense, specialist language for practitioners",
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

function getOptionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || value;
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

  const [selected, setSelected] = useState([]);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [responseMode, setResponseMode] = useState("researcher");
  const [answerMode, setAnswerMode] = useState("analysis");
  const [responseModeAnchor, setResponseModeAnchor] = useState(null);
  const [answerModeAnchor, setAnswerModeAnchor] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sessionId, setSessionId] = useState(resumeSessionId);

  // History state
  const [historySessions, setHistorySessions] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: "" });
  const [renameDialog, setRenameDialog] = useState({ open: false, sessionId: null, title: "" });
  const [deleteDialog, setDeleteDialog] = useState({ open: false, sessionId: null });

  const [citationDrawer, setCitationDrawer] = useState({
    open: false,
    citations: [],
    focusIndex: 0,
  });

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

  function restoreSession(detail) {
    setMessages(
      detail.messages.map((m) => ({
        role: m.role,
        content: m.content,
        citations: Array.isArray(m.citations) ? m.citations : [],
        evidenceSufficient: m.evidence_sufficient,
        responseMode: m.response_mode,
      })),
    );
    setSessionId(String(detail.id));
    if (detail.response_mode) setResponseMode(detail.response_mode);

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

  function drawerCitations(citations, focusIndex) {
    if (!citations || citations.length === 0) return [];
    if (citations.length > 12) {
      const start = Math.max(0, focusIndex - 1);
      const end = Math.min(citations.length, focusIndex + 4);
      return citations.slice(start, end).map((c, i) => ({ ...c, _displayIndex: start + i + 1 }));
    }
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

  function openCitationDrawer(citations, focusIndex = 0) {
    setCitationDrawer({ open: true, citations: citations || [], focusIndex });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const cleanQuestion = question.trim();
    if (!cleanQuestion || !selected.length || busy) return;

    setMessages((current) => [...current, { role: "user", content: cleanQuestion }]);
    setQuestion("");
    setBusy(true);
    setError("");

    try {
      const result = await askQuestion(
        cleanQuestion, selected, responseMode, answerMode, messages, sessionId,
      );
      if (!sessionId && result.session_id) {
        setSessionId(result.session_id);
        // Refresh history list so the new session appears
        loadSessions();
      }
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: result.answer,
          citations: Array.isArray(result.citations) ? result.citations : [],
          truncated: result.truncated,
          evidenceSufficient: result.evidence_sufficient,
          responseMode: result.response_mode || responseMode,
          answerMode: result.answer_mode || answerMode,
        },
      ]);
    } catch (chatError) {
      setError(chatError.message);
    } finally {
      setBusy(false);
    }
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
    <Box component="section">
      <Box sx={{ display: "flex", gap: 2, flexDirection: { xs: "column", md: "row" }, alignItems: "stretch" }}>

        {/* Left panel: Sources (top) + History (bottom) */}
        <Card
          sx={{
            p: 0,
            width: { xs: "100%", md: 280 },
            flexShrink: 0,
            display: "flex",
            flexDirection: "column",
            minHeight: { md: 520 },
          }}
        >
          {/* ── Sources section ── */}
          <Box sx={{ px: 3, pt: 3, pb: 1.5, flexShrink: 0 }}>
            <Typography variant="subtitle2">Context</Typography>
            <Typography variant="h2" sx={{ fontSize: 22, mb: 1.5 }}>Sources</Typography>
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
              <Box sx={{ maxHeight: 200, overflowY: "auto" }}>
                {sourceDocs.map((document) => (
                  <Box
                    key={document.id || document.name}
                    sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}
                  >
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={selected.includes(document.id)}
                          onChange={() => toggleDocument(document.id)}
                          size="small"
                        />
                      }
                      label={
                        <Typography variant="body2" sx={{ wordBreak: "break-word", fontSize: 13 }}>
                          {document.title || document.name}
                        </Typography>
                      }
                      sx={{ m: 0, flex: 1 }}
                    />
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
                sx={{ mt: 0.5, fontSize: "0.75em", color: "#214f42", textTransform: "none", px: 0 }}
              >
                + Add more sources
              </Button>
            )}
          </Box>

          <Divider />

          {/* ── History section ── */}
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

        {/* Chat Panel */}
        <Card sx={{ p: 3, flex: 1, minWidth: 0 }}>
          <Box
            sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: "20px" }}
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
          <Box sx={{ mb: 3, minHeight: 200 }}>
            {messages.length === 0 && (
              <Typography sx={{ py: 4, textAlign: "center", color: "text.secondary" }}>
                Ask a question to start a conversation.
              </Typography>
            )}
            {messages.map((message, index) => (
              <Box
                key={`${message.role}-${index}`}
                sx={{
                  mb: 2,
                  p: 2,
                  borderRadius: 2,
                  bgcolor: message.role === "user" ? "#f0f5f2" : "#fff",
                  border: "1px solid #e2e5df",
                  ...(message.evidenceSufficient === false && { borderColor: "#ffcdd2" }),
                }}
              >
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                  <Typography variant="body2" sx={{ fontWeight: 800 }}>
                    {message.role === "user" ? "You" : "Assistant"}
                  </Typography>
                  {message.role === "assistant" && (message.responseMode || message.answerMode) && (
                    <Typography component="small" variant="caption" sx={{ color: "text.secondary" }}>
                      {[
                        message.responseMode === "student" ? "Student" : "Policy Researcher",
                        message.answerMode === "chat" ? "Open Discussion" : "Document Analysis",
                      ].join(" · ")}
                    </Typography>
                  )}
                  {message.role === "assistant" && message.citations?.length > 0 && (
                    <Button
                      size="small"
                      variant="text"
                      onClick={() => openCitationDrawer(message.citations)}
                      sx={{
                        ml: "auto",
                        fontSize: "0.72em",
                        color: "#214f42",
                        textTransform: "none",
                        minWidth: 0,
                        px: 1,
                        py: 0,
                      }}
                    >
                      {message.citations.length} source{message.citations.length !== 1 ? "s" : ""}
                    </Button>
                  )}
                </Box>
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
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={makeMarkdownComponents(message.citations || [], openCitationDrawer)}
                    >
                      {message.content}
                    </ReactMarkdown>
                  </Box>
                ) : (
                  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                    {message.content}
                  </Typography>
                )}
                {message.role === "assistant" && message.evidenceSufficient !== false && (
                  <CitationList citations={message.citations} onOpenSource={handleOpenCitation} />
                )}
                {message.truncated && (
                  <Typography variant="caption" sx={{ color: "warning.main" }}>
                    The combined PDF text was truncated.
                  </Typography>
                )}
                {message.evidenceSufficient === false && message.answerMode === "chat" && (
                  <Typography variant="caption" sx={{ color: "text.secondary" }}>
                    Selected documents provided limited evidence; this answer may include general
                    knowledge beyond the excerpts.
                  </Typography>
                )}
                {message.evidenceSufficient === false && message.answerMode !== "chat" && (
                  <Typography variant="caption" sx={{ color: "text.secondary" }}>
                    Answer withheld because evidence was insufficient.
                  </Typography>
                )}
              </Box>
            ))}
            {busy && (
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, p: 2 }}>
                <CircularProgress size={20} />
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Thinking...
                </Typography>
              </Box>
            )}
          </Box>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          {/* Mode selectors */}
          <Box sx={{ mb: 2, display: "flex", flexWrap: "wrap", gap: 1.5, alignItems: "center" }}>
            <Box>
              <Typography variant="caption" sx={{ display: "block", mb: 0.5, color: "text.secondary" }}>
                Writing style
              </Typography>
              <Button
                variant="outlined"
                size="small"
                disabled={busy}
                endIcon={<ArrowDropDownIcon />}
                onClick={(event) => setResponseModeAnchor(event.currentTarget)}
                aria-haspopup="menu"
              >
                {getOptionLabel(RESPONSE_MODE_OPTIONS, responseMode)}
              </Button>
              <Menu
                anchorEl={responseModeAnchor}
                open={Boolean(responseModeAnchor)}
                onClose={() => setResponseModeAnchor(null)}
              >
                {RESPONSE_MODE_OPTIONS.map((option) => (
                  <MenuItem
                    key={option.value}
                    selected={option.value === responseMode}
                    onClick={() => { setResponseMode(option.value); setResponseModeAnchor(null); }}
                  >
                    <ListItemText primary={option.label} secondary={option.description} />
                  </MenuItem>
                ))}
              </Menu>
            </Box>

            <Box>
              <Typography variant="caption" sx={{ display: "block", mb: 0.5, color: "text.secondary" }}>
                Answer purpose
              </Typography>
              <Button
                variant="outlined"
                size="small"
                disabled={busy}
                endIcon={<ArrowDropDownIcon />}
                onClick={(event) => setAnswerModeAnchor(event.currentTarget)}
                aria-haspopup="menu"
              >
                {getOptionLabel(ANSWER_MODE_OPTIONS, answerMode)}
              </Button>
              <Menu
                anchorEl={answerModeAnchor}
                open={Boolean(answerModeAnchor)}
                onClose={() => setAnswerModeAnchor(null)}
              >
                {ANSWER_MODE_OPTIONS.map((option) => (
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
          </Box>

          {/* Chat Form */}
          <Box component="form" onSubmit={handleSubmit} sx={{ display: "flex", gap: 1 }}>
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
            <Button
              variant="contained"
              disabled={!question.trim() || !selected.length || busy}
              type="submit"
              sx={{ alignSelf: "flex-end", minWidth: 80 }}
              endIcon={<SendIcon />}
            >
              Send
            </Button>
          </Box>
        </Card>
      </Box>

      {/* Citation Drawer */}
      <Drawer
        anchor="right"
        open={citationDrawer.open}
        onClose={() => setCitationDrawer((s) => ({ ...s, open: false }))}
        PaperProps={{ sx: { width: { xs: "100%", sm: 380 }, p: 3, boxSizing: "border-box" } }}
      >
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
          <Typography variant="h6" sx={{ fontFamily: "Georgia, serif" }}>
            Sources
          </Typography>
          <IconButton onClick={() => setCitationDrawer((s) => ({ ...s, open: false }))} size="small">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>
        <Divider sx={{ mb: 2 }} />
        {citationDrawer.citations.length === 0 ? (
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            No citation details available for this answer.
          </Typography>
        ) : (
          drawerCitations(citationDrawer.citations, citationDrawer.focusIndex).map((c, i) => (
            <Box
              key={i}
              sx={{
                mb: 2,
                pb: 2,
                borderBottom: "1px solid #e2e5df",
                ...(c._displayIndex === citationDrawer.focusIndex + 1 && {
                  background: "#f0f5f2",
                  borderRadius: 1,
                  px: 1.5,
                  pt: 1,
                }),
              }}
            >
              <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.25 }}>
                [{c._displayIndex}] {c.title}
              </Typography>
              {c.page && (
                <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 0.5 }}>
                  Page {c.page}
                </Typography>
              )}
              {c.quote && (
                <Typography
                  variant="body2"
                  sx={{ color: "#63706a", fontStyle: "italic", fontSize: "0.82em", lineHeight: 1.55, mb: 1 }}
                >
                  &ldquo;{c.quote.length > 240 ? c.quote.slice(0, 240) + "…" : c.quote}&rdquo;
                </Typography>
              )}
              <Button
                size="small"
                variant="text"
                onClick={() => {
                  setCitationDrawer((s) => ({ ...s, open: false }));
                  onNavigate("library");
                }}
                sx={{ fontSize: "0.75em", color: "#214f42", textTransform: "none", px: 0 }}
              >
                View in Library →
              </Button>
            </Box>
          ))
        )}
      </Drawer>

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
