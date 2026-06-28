import { useEffect, useState } from "react";
import { getSettings, saveSettings } from "../api";

export default function SettingsPage({ user, onNavigate }) {
  const [settings, setSettings] = useState(null);
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function loadSettings() {
    setLoading(true);
    setError("");
    try {
      const result = await getSettings();
      setSettings(result);
      setModel(result.llm_chat_model || "");
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (user) loadSettings();
    else setLoading(false);
  }, [user]);

  async function handleSave(event) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await saveSettings({
        llm_api_key: apiKey.trim() ? apiKey : null,
        llm_chat_model: model,
      });
      setSettings(result);
      setModel(result.llm_chat_model || "");
      setApiKey("");
      setNotice("Token settings saved.");
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleClearToken() {
    if (!window.confirm("Clear the saved token and fall back to .env if present?")) return;

    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await saveSettings({
        llm_api_key: "",
        llm_chat_model: model,
      });
      setSettings(result);
      setApiKey("");
      setNotice("Saved token cleared.");
    } catch (clearError) {
      setError(clearError.message);
    } finally {
      setBusy(false);
    }
  }

  // requires admin login
  if (!user) {
    return (
      <section className="settings-layout">
        <div className="empty-state" style={{ width: "100%", marginTop: "40px" }}>
          <p>Access Denied. Administrator privileges required for settings.</p>
          <button className="button primary" onClick={() => onNavigate("auth")}>Go to Login</button>
        </div>
      </section>
    );
  }

  return (
    <section className="settings-layout">
      <aside className="settings-sidebar">
        <p className="eyebrow">Settings</p>
        <h2>Workspace setup</h2>
        <button className="settings-nav-item active" type="button">
          API token
        </button>
        <p className="muted">Saved values are kept on the backend and override the local .env file.</p>
      </aside>

      <div className="content-panel settings-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Configuration</p>
            <h2>API token</h2>
          </div>
        </div>

        {loading ? (
          <div className="empty-state">Loading settings...</div>
        ) : (
          <>
            <div className="token-status-grid">
              <div className="token-status-item">
                <span>Status</span>
                <strong>{settings?.llm_configured ? "Configured" : "Not configured"}</strong>
              </div>
              <div className="token-status-item">
                <span>Token</span>
                <strong>{settings?.masked_llm_api_key || "None"}</strong>
              </div>
              <div className="token-status-item">
                <span>Source</span>
                <strong>{settings?.llm_api_key_source || "missing"}</strong>
              </div>
              <div className="token-status-item">
                <span>Model source</span>
                <strong>{settings?.llm_chat_model_source || "default"}</strong>
              </div>
            </div>

            {notice && <div className="notice success">{notice}</div>}
            {error && <div className="notice error">{error}</div>}

            <form className="settings-form" onSubmit={handleSave}>
              <label className="settings-field full">
                <span>New API key</span>
                <input
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="Leave blank to keep the current token"
                  type="password"
                  autoComplete="off"
                />
                <small>Leave this empty to keep the token currently in use.</small>
              </label>
              <label className="settings-field">
                <span>Chat model</span>
                <input
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  placeholder="Enter the chat model name"
                />
              </label>
              <div className="settings-actions">
                <button className="button primary" disabled={busy} type="submit">
                  {busy ? "Saving..." : "Save settings"}
                </button>
                <button className="button ghost" disabled={busy} type="button" onClick={loadSettings}>
                  Reload
                </button>
                <button className="button danger" disabled={busy} type="button" onClick={handleClearToken}>
                  Clear saved token
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </section>
  );
}
