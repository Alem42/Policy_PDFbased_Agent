import { useState } from "react";

export default function AppMenu({ currentView, user, onNavigate }) {
  const [open, setOpen] = useState(false);

  function navigate(view) {
    onNavigate(view);
    setOpen(false);
  }

  return (
    <div className="app-menu">
      <button
        className="menu-trigger"
        type="button"
        aria-expanded={open}
        aria-label="Open navigation menu"
        onClick={() => setOpen((current) => !current)}
      >
        <span className="menu-icon" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <span>Menu</span>
      </button>
      {open && (
        <div className="menu-popover">
          <button
            className={currentView === "home" ? "active" : ""}
            type="button"
            onClick={() => navigate("home")}
          >
            Home
          </button>
          <button
            className={currentView === "library" ? "active" : ""}
            type="button"
            onClick={() => navigate("library")}
            disabled={!user}
          >
            Documents
          </button>
          <button
            className={currentView === "chat" ? "active" : ""}
            type="button"
            onClick={() => navigate("chat")}
            disabled={!user}
          >
            Question & answer
          </button>
          {user?.role === "admin" && (
            <button
              className={currentView === "settings" ? "active" : ""}
              type="button"
              onClick={() => navigate("settings")}
            >
              Token settings
            </button>
          )}
        </div>
      )}
    </div>
  );
}
