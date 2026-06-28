import { createBrowserRouter, Navigate, useOutletContext } from "react-router-dom";
import App from "./App";
import AdminDashboard from "./pages/AdminDashboard";
import AuthPage from "./pages/AuthPage";
import ChatPage from "./pages/ChatPage";
import HomePage from "./pages/HomePage";
import LibraryPage from "./pages/LibraryPage";
import SettingsPage from "./pages/SettingsPage";
import { ROUTES } from "./routes";

function HomeRoute() {
  const { documents, loading, user, handleDocumentsChanged, navigateToView } = useOutletContext();
  return (
    <HomePage
      documents={documents}
      loading={loading}
      user={user}
      onDocumentsChanged={handleDocumentsChanged}
      onNavigate={navigateToView}
    />
  );
}

function AuthRoute() {
  const { handleAuthenticated, navigateToView } = useOutletContext();
  return <AuthPage onAuthenticated={handleAuthenticated} onNavigate={navigateToView} />;
}

function ChatRoute() {
  const {
    documents,
    user,
    contextSourceIds,
    handleRemoveSource,
    navigateToView,
  } = useOutletContext();
  return (
    <ChatPage
      documents={documents}
      user={user}
      onNavigate={navigateToView}
      contextSourceIds={contextSourceIds}
      onRemoveSource={handleRemoveSource}
    />
  );
}

function LibraryRoute() {
  const {
    documents,
    loading,
    user,
    loadDocuments,
    handleRescanDocuments,
    handleDocumentsChanged,
    navigateToView,
    contextSourceIds,
    handleAddSource,
    handleRemoveSource,
  } = useOutletContext();
  return (
    <LibraryPage
      documents={documents}
      loading={loading}
      user={user}
      onRefresh={loadDocuments}
      onRescan={handleRescanDocuments}
      onDocumentsChanged={handleDocumentsChanged}
      onNavigate={navigateToView}
      contextSourceIds={contextSourceIds}
      onAddSource={handleAddSource}
      onRemoveSource={handleRemoveSource}
    />
  );
}

function AdminRoute() {
  const { documents, loading, user, handleDocumentsChanged, navigateToView } = useOutletContext();
  return (
    <AdminDashboard
      documents={documents}
      loading={loading}
      user={user}
      onDocumentsChanged={handleDocumentsChanged}
      onNavigate={navigateToView}
    />
  );
}

function SettingsRoute() {
  const { user, navigateToView } = useOutletContext();
  return <SettingsPage user={user} onNavigate={navigateToView} />;
}

export const router = createBrowserRouter([
  {
    path: ROUTES.root,
    element: <App />,
    children: [
      { index: true, element: <Navigate to={ROUTES.chat} replace /> },
      { path: ROUTES.home.slice(1), element: <HomeRoute /> },
      { path: ROUTES.chat.slice(1), element: <ChatRoute /> },
      { path: ROUTES.library.slice(1), element: <LibraryRoute /> },
      { path: ROUTES.admin.slice(1), element: <AdminRoute /> },
      { path: ROUTES.settings.slice(1), element: <SettingsRoute /> },
      { path: ROUTES.auth.slice(1), element: <AuthRoute /> },
      { path: "*", element: <Navigate to={ROUTES.chat} replace /> },
    ],
  },
]);
