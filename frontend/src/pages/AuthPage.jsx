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
} from "@mui/material";
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
    <Box
      component="section"
      sx={{
        display: "flex",
        justifyContent: "center",
        pt: "60px",
        pb: "60px",
      }}
    >
      <Card sx={{ maxWidth: 440, width: "100%", p: 3 }}>
        <CardContent sx={{ p: "0 !important" }}>
          {mode === "login" ? (
            <>
              <Typography variant="subtitle2">Restricted Access</Typography>
              <Typography variant="h1" sx={{ fontSize: "clamp(36px, 5vw, 56px)" }}>
                Admin Login
              </Typography>
              <Typography variant="body2" sx={{ mt: 2, color: "text.secondary" }}>
                Knowledge base management requires administrator credentials.
              </Typography>

              {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}

              <Box component="form" onSubmit={handleLogin} sx={{ mt: 3, display: "grid", gap: 2 }}>
                <Box sx={{ display: "grid", gap: 0.5 }}>
                  <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                    Username
                  </Typography>
                  <TextField
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
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
                    onChange={(event) => setPassword(event.target.value)}
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
                    Register a new account
                  </Button>
                  <Button variant="outlined" type="button" onClick={() => onNavigate("chat")} fullWidth>
                    Back to Public Site
                  </Button>
                </Box>
              </Box>
            </>
          ) : (
            <>
              <Typography variant="subtitle2">Account Setup</Typography>
              <Typography variant="h1" sx={{ fontSize: "clamp(36px, 5vw, 56px)" }}>
                Register
              </Typography>
              <Typography variant="body2" sx={{ mt: 2, color: "text.secondary" }}>
                Create a new account. Role can be set to user or admin for testing.
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
                    onChange={(event) => setUsername(event.target.value)}
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
                    onChange={(event) => setPassword(event.target.value)}
                    type="password"
                    autoComplete="new-password"
                    fullWidth
                    size="small"
                  />
                </Box>
                <Box sx={{ display: "grid", gap: 0.5 }}>
                  <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                    Role
                  </Typography>
                  <FormControl size="small" fullWidth>
                    <Select value={role} onChange={(event) => setRole(event.target.value)}>
                      <MenuItem value="user">User (Policy Researcher)</MenuItem>
                      <MenuItem value="admin">Admin</MenuItem>
                    </Select>
                  </FormControl>
                </Box>

                <Box sx={{ display: "flex", flexDirection: "column", gap: 1, mt: 1 }}>
                  <Button variant="contained" disabled={busy} type="submit" fullWidth>
                    {busy ? "Registering..." : "Register"}
                  </Button>
                  <Button variant="outlined" type="button" onClick={() => switchMode("login")} fullWidth>
                    Back to Login
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
