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
          {/* public access */}
          <button
            className={currentView === "home" ? "active" : ""}
            type="button"
            onClick={() => navigate("home")}
          >
            Overview
          </button>
          <button
            className={currentView === "chat" ? "active" : ""}
            type="button"
            onClick={() => navigate("chat")}
          >
            Question & Answer
          </button>
          <button
            className={currentView === "library" ? "active" : ""}
            type="button"
            onClick={() => navigate("library")}
          >
            Document Library
          </button>
          
          {/* admin access */}
          {user && (
            <>
              <div className="menu-divider" style={{ margin: "8px 0", borderTop: "1px solid #eee" }}></div>
              <button
                className={currentView === "admin" ? "active" : ""}
                type="button"
                onClick={() => navigate("admin")}
              >
                Dashboard
              </button>
              <button
                className={currentView === "settings" ? "active" : ""}
                type="button"
                onClick={() => navigate("settings")}
              >
                Token Settings
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
