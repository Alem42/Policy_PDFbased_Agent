import { useState } from "react";
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Alert,
} from "@mui/material";
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
          <Typography variant="subtitle2">Restricted Access</Typography>
          <Typography variant="h1" sx={{ fontSize: "clamp(36px, 5vw, 56px)" }}>
            Admin Login
          </Typography>
          <Typography variant="body2" sx={{ mt: 2, color: "text.secondary" }}>
            Knowledge base management requires administrator credentials.
          </Typography>

          {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}

          <Box component="form" onSubmit={handleSubmit} sx={{ mt: 3, display: "grid", gap: 2 }}>
            <Box sx={{ display: "grid", gap: 0.5 }}>
              <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
                Admin Username
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
              <Button
                variant="contained"
                disabled={busy}
                type="submit"
                fullWidth
              >
                {busy ? "Authenticating..." : "Log in"}
              </Button>
              <Button
                variant="outlined"
                onClick={() => onNavigate("chat")}
                fullWidth
              >
                Back to User Dashboard
              </Button>
            </Box>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}