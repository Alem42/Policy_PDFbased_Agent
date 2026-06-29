import { useEffect, useState } from "react";
import {
  Box,
  Card,
  Typography,
  Button,
  Checkbox,
  FormControlLabel,
  TextField,
  Alert,
  ToggleButtonGroup,
  ToggleButton,
  IconButton,
  CircularProgress,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import SendIcon from "@mui/icons-material/Send";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { askQuestion } from "../api";

export default function ChatPage({
  documents,
  user,
  onNavigate,
  contextSourceIds = [],
  onRemoveSource,
}) {
  if (!user) {
    return (
      <Box
        sx={{ display: "flex", justifyContent: "center", alignItems: "flex-start", pt: 8 }}
      >
        <Card sx={{ p: 4, maxWidth: 420, width: "100%", textAlign: "center" }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Authentication required
          </Typography>
          <Typography variant="h2" sx={{ fontSize: 24, mb: 2 }}>
            Sign in to use Chat
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary", mb: 3 }}>
            The Q&amp;A chat is only available to registered users. Please log in or create
            an account to continue.
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setSelected((current) => {
      const stillSelected = current.filter((id) => contextSourceIds.includes(id));
      const newSources = contextSourceIds.filter((id) => !current.includes(id));
      return [...stillSelected, ...newSources];
    });
  }, [contextSourceIds]);

  const sourceDocs = documents.filter((doc) => contextSourceIds.includes(doc.id));

  function toggleDocument(documentId) {
    setSelected((current) =>
      current.includes(documentId)
        ? current.filter((id) => id !== documentId)
        : [...current, documentId],
    );
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
      const result = await askQuestion(cleanQuestion, selected, responseMode);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: result.answer,
          truncated: result.truncated,
          evidenceSufficient: result.evidence_sufficient,
          responseMode: result.response_mode || responseMode,
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

  return (
    <Box component="section">
      <Box sx={{ display: "flex", gap: 2, flexDirection: { xs: "column", md: "row" } }}>
        {/* Source Panel */}
        <Card sx={{ p: 3, width: { xs: "100%", md: 280 }, flexShrink: 0 }}>
          <Typography variant="subtitle2">Context</Typography>
          <Typography variant="h2" sx={{ fontSize: 24 }}>Sources</Typography>
          <Box sx={{ mt: 2 }}>
            {sourceDocs.length === 0 ? (
              <Box sx={{ py: 4, textAlign: "center" }}>
                <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
                  No source files in the context right now.
                </Typography>
                <Button variant="outlined" onClick={() => onNavigate("library")}>
                  Find relevant files
                </Button>
              </Box>
            ) : (
              sourceDocs.map((document) => (
                <Box
                  key={document.id || document.name}
                  sx={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    mb: 1,
                  }}
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
                      <Typography variant="body2" sx={{ wordBreak: "break-word" }}>
                        {document.title || document.name}
                      </Typography>
                    }
                    sx={{ m: 0, flex: 1 }}
                  />
                  <IconButton
                    size="small"
                    title="Remove from context"
                    onClick={() => onRemoveSource(document.id)}
                    sx={{ color: "#999" }}
                  >
                    <CloseIcon fontSize="small" />
                  </IconButton>
                </Box>
              ))
            )}
          </Box>
        </Card>

        {/* Chat Panel */}
        <Card sx={{ p: 3, flex: 1, minWidth: 0 }}>
          <Box
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              mb: "20px",
            }}
          >
            <Box>
              <Typography variant="subtitle2">Conversation</Typography>
              <Typography variant="h2" sx={{ fontSize: 24 }}>Chat</Typography>
            </Box>
            <Button
              variant="outlined"
              onClick={() => {
                setMessages([]);
                setError("");
              }}
            >
              Clear Chat
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
                  ...(message.evidenceSufficient === false && {
                    borderColor: "#ffcdd2",
                  }),
                }}
              >
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                  <Typography variant="body2" sx={{ fontWeight: 800 }}>
                    {message.role === "user" ? "You" : "Assistant"}
                  </Typography>
                  {message.role === "assistant" && message.responseMode && (
                    <Typography
                      component="small"
                      variant="caption"
                      sx={{ color: "text.secondary" }}
                    >
                      {message.responseMode === "student" ? "Student mode" : "Policy researcher mode"}
                    </Typography>
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
                        px: 0.75,
                        py: 0.25,
                        borderRadius: 1,
                        bgcolor: "#f0f3ed",
                        fontSize: "0.9em",
                        fontFamily: "monospace",
                      },
                      "& pre": {
                        p: 2,
                        borderRadius: 2,
                        bgcolor: "#f5f5f0",
                        overflow: "auto",
                        fontSize: "0.85em",
                        "& code": { p: 0, bgcolor: "transparent" },
                      },
                      "& blockquote": {
                        mx: 0,
                        px: 2,
                        borderLeft: "3px solid #214f42",
                        color: "#63706a",
                      },
                      "& table": { borderCollapse: "collapse", width: "100%", my: 1 },
                      "& th, & td": { border: "1px solid #d9d8d0", px: 1.5, py: 1, textAlign: "left" },
                      "& th": { bgcolor: "#f5f5f0", fontWeight: 800 },
                      "& a": { color: "#214f42" },
                    }}
                  >
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {message.content}
                    </ReactMarkdown>
                  </Box>
                ) : (
                  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                    {message.content}
                  </Typography>
                )}
                {message.truncated && (
                  <Typography variant="caption" sx={{ color: "warning.main" }}>
                    The combined PDF text was truncated.
                  </Typography>
                )}
                {message.evidenceSufficient === false && (
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

          {/* Mode Toggle */}
          <Box sx={{ mb: 2 }}>
            <Typography variant="body2" sx={{ fontWeight: 800, mb: 1 }}>
              Response mode
            </Typography>
            <ToggleButtonGroup
              value={responseMode}
              exclusive
              onChange={(_, newMode) => newMode && setResponseMode(newMode)}
              disabled={busy}
              size="small"
            >
              <ToggleButton value="researcher">Policy Researcher</ToggleButton>
              <ToggleButton value="student">Student</ToggleButton>
            </ToggleButtonGroup>
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
    </Box>
  );
}