import { useState } from "react";
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Alert,
  Select,
  MenuItem,
  FormControl,
  ToggleButtonGroup,
  ToggleButton,
} from "@mui/material";
import { login, register, saveAuth } from "../api";

// mode: "login" | "register"
// loginType: "user" | "admin"

export default function AuthPage({ onAuthenticated, onNavigate }) {
  const [mode, setMode] = useState("login");
  const [loginType, setLoginType] = useState("user");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const [secret, setSecret] = useState("");
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
    setSecret("");
  }

  function handleLoginTypeChange(_, next) {
    if (!next) return;
    setLoginType(next);
    setError("");
  }

  async function handleLogin(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const auth = await login(username, password);
      saveAuth(auth);
      onAuthenticated(auth.user);
      // Redirect based on actual role
      if (auth.user.role === "admin") {
        onNavigate("admin");
      } else {
        onNavigate("chat");
      }
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
      await register(username, password, role, role === "admin" ? secret : undefined);
      setNotice(`Account "${username}" registered. You can now log in.`);
      setUsername("");
      setPassword("");
      setRole("user");
      setSecret("");
    } catch (regError) {
      setError(regError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box
      component="section"
      sx={{ display: "flex", justifyContent: "center", pt: "60px", pb: "60px" }}
    >
      <Card sx={{ maxWidth: 440, width: "100%", p: 3 }}>
        <CardContent sx={{ p: "0 !important" }}>
          {mode === "login" ? (
            <>
              <Typography variant="subtitle2">Welcome back</Typography>
              <Typography variant="h1" sx={{ fontSize: "clamp(32px, 5vw, 48px)" }}>
                Log in
              </Typography>

              {/* User / Admin toggle */}
              <ToggleButtonGroup
                value={loginType}
                exclusive
                onChange={handleLoginTypeChange}
                size="small"
                sx={{ mt: 2 }}
              >
                <ToggleButton value="user" sx={{ px: 2.5 }}>
                  User Login
                </ToggleButton>
                <ToggleButton value="admin" sx={{ px: 2.5 }}>
                  Admin Login
                </ToggleButton>
              </ToggleButtonGroup>

              <Typography variant="body2" sx={{ mt: 1.5, color: "text.secondary" }}>
                {loginType === "admin"
                  ? "Knowledge base management requires administrator credentials."
                  : "Log in to access the policy Q&A chat."}
              </Typography>

              {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}

              <Box component="form" onSubmit={handleLogin} sx={{ mt: 3, display: "grid", gap: 2 }}>
                <Box sx={{ display: "grid", gap: 0.5 }}>
                  <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                    Username
                  </Typography>
                  <TextField
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="username"
                    fullWidth
                    size="small"
                  />
                </Box>
                <Box sx={{ display: "grid", gap: 0.5 }}>
                  <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                    Password
                  </Typography>
                  <TextField
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    type="password"
                    autoComplete="current-password"
                    fullWidth
                    size="small"
                  />
                </Box>

                <Box sx={{ display: "flex", flexDirection: "column", gap: 1, mt: 1 }}>
                  <Button variant="contained" disabled={busy} type="submit" fullWidth>
                    {busy ? "Authenticating..." : "Log in"}
                  </Button>
                  <Button variant="outlined" type="button" onClick={() => switchMode("register")} fullWidth>
                    Create an account
                  </Button>
                  <Button variant="text" type="button" onClick={() => onNavigate("library")} fullWidth>
                    Browse library without logging in
                  </Button>
                </Box>
              </Box>
            </>
          ) : (
            <>
              <Typography variant="subtitle2">New account</Typography>
              <Typography variant="h1" sx={{ fontSize: "clamp(32px, 5vw, 48px)" }}>
                Register
              </Typography>
              <Typography variant="body2" sx={{ mt: 2, color: "text.secondary" }}>
                Create an account to access the chat and document library.
              </Typography>

              {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
              {notice && <Alert severity="success" sx={{ mt: 2 }}>{notice}</Alert>}

              <Box component="form" onSubmit={handleRegister} sx={{ mt: 3, display: "grid", gap: 2 }}>
                <Box sx={{ display: "grid", gap: 0.5 }}>
                  <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                    Username
                  </Typography>
                  <TextField
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="username"
                    fullWidth
                    size="small"
                  />
                </Box>
                <Box sx={{ display: "grid", gap: 0.5 }}>
                  <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                    Password
                  </Typography>
                  <TextField
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    type="password"
                    autoComplete="new-password"
                    fullWidth
                    size="small"
                  />
                </Box>
                <Box sx={{ display: "grid", gap: 0.5 }}>
                  <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                    Account type
                  </Typography>
                  <FormControl size="small" fullWidth>
                    <Select value={role} onChange={(e) => { setRole(e.target.value); setSecret(""); }}>
                      <MenuItem value="user">User (Policy Researcher)</MenuItem>
                      <MenuItem value="admin">Admin</MenuItem>
                    </Select>
                  </FormControl>
                </Box>

                {role === "admin" && (
                  <Box sx={{ display: "grid", gap: 0.5 }}>
                    <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                      Admin registration secret
                    </Typography>
                    <TextField
                      value={secret}
                      onChange={(e) => setSecret(e.target.value)}
                      type="password"
                      placeholder="Enter the secret issued by your administrator"
                      fullWidth
                      size="small"
                    />
                    <Typography variant="caption" sx={{ color: "text.secondary" }}>
                      Contact your system administrator to obtain this secret.
                    </Typography>
                  </Box>
                )}

                <Box sx={{ display: "flex", flexDirection: "column", gap: 1, mt: 1 }}>
                  <Button variant="contained" disabled={busy} type="submit" fullWidth>
                    {busy ? "Registering..." : "Create account"}
                  </Button>
                  <Button variant="outlined" type="button" onClick={() => switchMode("login")} fullWidth>
                    Back to login
                  </Button>
                </Box>
              </Box>
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
