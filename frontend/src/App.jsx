import { useEffect, useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { Box, Container, Alert } from "@mui/material";
import { clearAuth, getCurrentUser, getDocuments, getProcessingStatus, getStoredUser, rescanDocuments } from "./api";
import AppHeader from "./components/AppHeader";
import { chatSessionPath, getViewFromPath, ROUTES, VIEW_PATHS } from "./routes";

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [documents, setDocuments] = useState([]);
  const [user, setUser] = useState(getStoredUser());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [contextSourceIds, setContextSourceIds] = useState([]);
  // The most recently visited chat URL (bare /chat or /chat/<sessionId>).
  // Lets "Go to chat" and the header's Chat nav return to the conversation
  // the user left, instead of always starting a blank one.
  const [lastChatPath, setLastChatPath] = useState(ROUTES.chat);
  // The chat session ChatPage currently has open, if any. Lets ChatPage tell
  // a same-session remount (e.g. Library -> "Go to chat" round trip) apart
  // from switching to a different saved conversation: on a same-session
  // return, sources just added in Library must survive, not be clobbered by
  // that session's last-persisted document_ids.
  const [activeChatSessionId, setActiveChatSessionId] = useState(null);

  const documentCount = useMemo(() => documents.length, [documents]);
  const activeView = getViewFromPath(location.pathname);

  useEffect(() => {
    if (location.pathname === ROUTES.chat || location.pathname.startsWith(`${ROUTES.chat}/`)) {
      setLastChatPath(location.pathname);
    }
  }, [location.pathname]);

  function navigateToView(view, options) {
    if (view === "chat") {
      const path = options?.sessionId ? chatSessionPath(options.sessionId) : lastChatPath;
      navigate(path, options?.replace ? { replace: true } : undefined);
      return;
    }
    navigate(VIEW_PATHS[view] || ROUTES.chat, options);
  }

  async function loadDocuments() {
    setLoading(true);
    setError("");
    try {
      const result = await getDocuments();
      setDocuments(result.documents);
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    async function restoreUser() {
      if (!getStoredUser()) {
        setLoading(false);
        return;
      }
      try {
        setUser(await getCurrentUser());
      } catch {
        clearAuth();
        setUser(null);
      }
    }
    restoreUser();
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [user]);

  async function handleDocumentsChanged(documentIds) {
    if (!documentIds || documentIds.length === 0) {
      await loadDocuments();
      return;
    }

    // Poll for document processing status until all docs are ready or failed
    const maxAttempts = 40; // 2 minutes at 3s intervals
    let allReady = false;

    for (let attempt = 0; attempt < maxAttempts && !allReady; attempt++) {
      await new Promise((r) => setTimeout(r, attempt === 0 ? 0 : 3000)); // First check immediately

      try {
        const statuses = await Promise.all(
          documentIds.map((id) => getProcessingStatus(id).catch(() => ({ status: "queued" }))),
        );

        allReady = statuses.every(
          (s) => s.status === "indexed" || s.status === "ready" || s.status === "failed",
        );

        if (allReady) {
          await loadDocuments();
          break;
        }
      } catch {
        // Continue polling on error
      }
    }

    if (!allReady) {
      // Final refresh even if not all docs are ready
      await loadDocuments();
    }
  }

  async function handleRescanDocuments() {
    await rescanDocuments();
    await loadDocuments();
  }

  function handleAddSource(documentId, document = null) {
    if (document) {
      setDocuments((current) =>
        current.some((item) => item.id === documentId) ? current : [document, ...current]
      );
    }
    setContextSourceIds((prev) =>
      prev.includes(documentId) ? prev : [...prev, documentId]
    );
  }

  function handleRemoveSource(documentId) {
    setContextSourceIds((prev) => prev.filter((id) => id !== documentId));
  }

  function handleSetSources(documentIds) {
    setContextSourceIds(documentIds);
  }

  function handleLogout() {
    clearAuth();
    setUser(null);
    setContextSourceIds([]);
    // A logged-out visitor shouldn't land back on someone's private session.
    setLastChatPath(ROUTES.chat);
    setActiveChatSessionId(null);
    navigate(ROUTES.chat, { replace: true });
  }

  function handleAuthenticated(nextUser) {
    setUser(nextUser);
  }

  // The chat view fills the full viewport height with fixed, internally
  // scrolling panels (like ChatGPT/DeepSeek); every other view keeps the
  // normal document flow where the whole page scrolls. Width is untouched
  // either way — only this view's vertical layout behaves differently.
  const isChatView = activeView === "chat";

  return (
    <Container
      maxWidth="lg"
      sx={
        isChatView
          ? { height: "100vh", display: "flex", flexDirection: "column", pb: 0 }
          : { pb: 8 }
      }
    >
      <Box sx={{ flexShrink: 0 }}>
        <AppHeader
          currentView={activeView}
          documentCount={documentCount}
          user={user}
          onLogout={handleLogout}
          onNavigate={navigateToView}
        />
        {error && <Alert severity="error" sx={{ my: 2 }}>{error}</Alert>}
      </Box>

      <Box
        sx={
          isChatView
            ? { flex: 1, minHeight: 0, overflow: "hidden", display: "flex", flexDirection: "column", pt: 2, pb: 2 }
            : undefined
        }
      >
        <Outlet
          context={{
            documents,
            loading,
            user,
            contextSourceIds,
            activeChatSessionId,
            loadDocuments,
            handleDocumentsChanged,
            handleRescanDocuments,
            handleAddSource,
            handleRemoveSource,
            handleSetSources,
            handleActiveChatSessionChange: setActiveChatSessionId,
            handleAuthenticated,
            navigateToView,
          }}
        />
      </Box>
    </Container>
  );
}
