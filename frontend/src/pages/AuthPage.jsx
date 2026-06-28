import { useState } from "react";
import { login, saveAuth } from "../api";

export default function AuthPage({ onAuthenticated, onNavigate }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      // 仅保留 login 逻辑
      const auth = await login(username, password);
      saveAuth(auth);
      onAuthenticated(auth.user);
      onNavigate("admin");
    } catch (authError) {
      setError(authError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="auth-page">
      <div className="content-panel auth-card">
        <p className="eyebrow">Restricted Access</p>
        <h1>Admin Login</h1>
        <p className="muted">
          Knowledge base management requires administrator credentials.
        </p>

        {error && <div className="notice error">{error}</div>}

        <form className="settings-form auth-form" onSubmit={handleSubmit}>
          <label className="settings-field full">
            <span>Admin Username</span>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
            />
          </label>
          <label className="settings-field full">
            <span>Password</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              autoComplete="current-password"
            />
          </label>
          
          <div className="settings-actions">
            <button className="button primary full-width" disabled={busy} type="submit">
              {busy ? "Authenticating..." : "Log in"}
            </button>
            <button 
              className="button ghost full-width" 
              type="button" 
              onClick={() => onNavigate("chat")}
            >
              Back to User Dashboard
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}