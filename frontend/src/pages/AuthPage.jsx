import { useState } from "react";
import { login, register, saveAuth } from "../api";

export default function AuthPage({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const auth =
        mode === "login"
          ? await login(username, password)
          : await register(username, password, role);
      saveAuth(auth);
      onAuthenticated(auth.user);
    } catch (authError) {
      setError(authError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="auth-page">
      <div className="content-panel auth-card">
        <p className="eyebrow">{mode === "login" ? "Welcome back" : "Create account"}</p>
        <h1>{mode === "login" ? "Log in" : "Register"}</h1>
        <p className="muted">
          Guests can view the home page. Document search and Q&A require an account.
        </p>

        {error && <div className="notice error">{error}</div>}

        <form className="settings-form auth-form" onSubmit={handleSubmit}>
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
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>
          {mode === "register" && (
            <label className="settings-field">
              <span>Role</span>
              <select value={role} onChange={(event) => setRole(event.target.value)}>
                <option value="user">Normal user</option>
                <option value="admin">Administrator</option>
              </select>
            </label>
          )}
          <div className="settings-actions">
            <button className="button primary" disabled={busy} type="submit">
              {busy ? "Working..." : mode === "login" ? "Log in" : "Register"}
            </button>
            <button
              className="button ghost"
              type="button"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError("");
              }}
            >
              {mode === "login" ? "Create account" : "Use existing account"}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
