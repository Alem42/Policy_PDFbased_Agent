import { useEffect, useMemo, useState } from "react";
import { clearAuth, getCurrentUser, getDocuments, getStoredUser, rescanDocuments } from "./api";
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
          onDocumentsChanged={loadDocuments}
        />
      )}
      {activeView === "home" && (
        <HomePage
          documents={documents}
          loading={loading}
          user={user}
          onDocumentsChanged={loadDocuments}
          onNavigate={setActiveView}
        />
      )}
    </main>
  );
}
