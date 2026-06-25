import AppMenu from "./AppMenu";

export default function AppHeader({ currentView, documentCount, user, onLogout, onNavigate }) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <AppMenu currentView={currentView} user={user} onNavigate={onNavigate} />
        <button className="brand" type="button" onClick={() => onNavigate("home")}>
          <span className="brand-mark">P</span>
          <span>
            <strong>PDF Assistant</strong>
            <small>Document workspace</small>
          </span>
        </button>
      </div>
      <div className="status-pill">
        <span aria-hidden="true" />
        {user ? `${documentCount} document${documentCount === 1 ? "" : "s"}` : "Guest"}
      </div>
      {user ? (
        <button className="button ghost" type="button" onClick={onLogout}>
          {user.username} ({user.role}) - Log out
        </button>
      ) : (
        <button className="button primary" type="button" onClick={() => onNavigate("auth")}>
          Log in
        </button>
      )}
    </header>
  );
}
