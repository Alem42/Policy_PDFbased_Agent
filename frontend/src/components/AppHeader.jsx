import AppMenu from "./AppMenu";

export default function AppHeader({ currentView, documentCount, user, onLogout, onNavigate }) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <AppMenu currentView={currentView} user={user} onNavigate={onNavigate} />
        <button className="brand" type="button" onClick={() => onNavigate("chat")}>
          <span className="brand-mark">P</span>
          <span>
            <strong>Policy in Action Library</strong>
            <small>Formulate Policy Like an Expert</small>
          </span>
        </button>
      </div>
      <div className="status-pill">
        <span aria-hidden="true" />
        {user ? `Admin Workspace - ${documentCount} document${documentCount === 1 ? "" : "s"}` : "Public Workspace"}
      </div>
      {user ? (
        <button className="button ghost" type="button" onClick={onLogout}>
          {user.username} - Log out
        </button>
      ) : (
        <button className="button primary" type="button" onClick={() => onNavigate("auth")}>
          Admin Login
        </button>
      )}
    </header>
  );
}
