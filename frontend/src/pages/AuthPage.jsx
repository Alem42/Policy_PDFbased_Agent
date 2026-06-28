import { useState } from "react";
import { login, register, saveAuth } from "../api";

export default function AuthPage({ onAuthenticated, onNavigate }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function switchMode(next) {
    setMode(next);
    setError("");
    setNotice("");
    setUsername("");
    setPassword("");
    setRole("user");
  }

  async function handleLogin(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
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

  async function handleRegister(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await register(username, password, role);
      setNotice(`User "${username}" registered successfully. You can now log in.`);
      setUsername("");
      setPassword("");
      setRole("user");
    } catch (regError) {
      setError(regError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="auth-page">
      <div className="content-panel auth-card">
        {mode === "login" ? (
          <>
            <p className="eyebrow">Restricted Access</p>
            <h1>Admin Login</h1>
            <p className="muted">
              Knowledge base management requires administrator credentials.
            </p>

            {error && <div className="notice error">{error}</div>}

            <form className="settings-form auth-form" onSubmit={handleLogin}>
              <label className="settings-field full">
                <span>Username</span>
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
                  onClick={() => switchMode("register")}
                >
                  Register a new account
                </button>
                <button
                  className="button ghost full-width"
                  type="button"
                  onClick={() => onNavigate("chat")}
                >
                  Back to Public Site
                </button>
              </div>
            </form>
          </>
        ) : (
          <>
            <p className="eyebrow">Account Setup</p>
            <h1>Register</h1>
            <p className="muted">
              Create a new account. Role can be set to user or admin for testing.
            </p>

            {error && <div className="notice error">{error}</div>}
            {notice && <div className="notice success">{notice}</div>}

            <form className="settings-form auth-form" onSubmit={handleRegister}>
              <label className="settings-field full">
                <span>Username</span>
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
                  autoComplete="new-password"
                />
              </label>
              <label className="settings-field full">
                <span>Role</span>
                <select value={role} onChange={(event) => setRole(event.target.value)}>
                  <option value="user">User (Policy Researcher)</option>
                  <option value="admin">Admin</option>
                </select>
              </label>

              <div className="settings-actions">
                <button className="button primary full-width" disabled={busy} type="submit">
                  {busy ? "Registering..." : "Register"}
                </button>
                <button
                  className="button ghost full-width"
                  type="button"
                  onClick={() => switchMode("login")}
                >
                  Back to Login
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </section>
  );
}
