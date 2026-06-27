import { useEffect, useMemo, useState } from "react";
import { clearAuth, getCurrentUser, getDocuments, getProcessingStatus, getStoredUser, rescanDocuments } from "./api";
import AppHeader from "./components/AppHeader";
import AuthPage from "./pages/AuthPage";
import ChatPage from "./pages/ChatPage";
import HomePage from "./pages/HomePage";
import LibraryPage from "./pages/LibraryPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  const [activeView, setActiveView] = useState("home");
  const [documents, setDocuments] = useState([]);
  const [user, setUser] = useState(getStoredUser());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const documentCount = useMemo(() => documents.length, [documents]);

  async function loadDocuments() {
    if (!user) {
      setDocuments([]);
      setLoading(false);
      return;
    }
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

  function handleLogout() {
    clearAuth();
    setUser(null);
    setDocuments([]);
    setActiveView("home");
  }

  function handleAuthenticated(nextUser) {
    setUser(nextUser);
    setActiveView("library");
  }

  return (
    <main className="app-shell">
      <AppHeader
        currentView={activeView}
        documentCount={documentCount}
        user={user}
        onLogout={handleLogout}
        onNavigate={setActiveView}
      />

      {error && <div className="notice error">{error}</div>}

      {activeView === "auth" && <AuthPage onAuthenticated={handleAuthenticated} />}
      {activeView === "settings" && user?.role === "admin" && <SettingsPage />}
      {activeView === "chat" && user && <ChatPage documents={documents} />}
      {activeView === "library" && user && (
        <LibraryPage
          documents={documents}
          loading={loading}
          user={user}
          onRefresh={loadDocuments}
          onRescan={handleRescanDocuments}
          onDocumentsChanged={handleDocumentsChanged}
        />
      )}
      {activeView === "home" && (
        <HomePage
          documents={documents}
          loading={loading}
          user={user}
          onDocumentsChanged={handleDocumentsChanged}
          onNavigate={setActiveView}
        />
      )}
    </main>
  );
}
