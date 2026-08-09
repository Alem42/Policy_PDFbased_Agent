import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  Checkbox,
  FormControl,
  FormControlLabel,
  IconButton,
  InputAdornment,
  MenuItem,
  Select,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import {
  AutoAwesomeOutlined,
  LockOutlined,
  VisibilityOffOutlined,
  VisibilityOutlined,
} from "@mui/icons-material";
import { login, register, saveAuth } from "../api";

const GREEN = "#214f42";

function Label({ children }) {
  return (
    <Typography component="span" variant="body2" sx={{ fontWeight: 800 }}>
      {children}
    </Typography>
  );
}

function PasswordField({ label, value, onChange, autoComplete, visible, onToggle, sx }) {
  return (
    <Box sx={{ display: "grid", gap: 0.5, ...sx }}>
      <Label>{label}</Label>
      <TextField
        value={value}
        onChange={onChange}
        type={visible ? "text" : "password"}
        autoComplete={autoComplete}
        fullWidth
        size="small"
        required
        InputProps={{
          endAdornment: (
            <InputAdornment position="end">
              <IconButton onClick={onToggle} edge="end" aria-label={`${visible ? "Hide" : "Show"} ${label.toLowerCase()}`}>
                {visible ? <VisibilityOffOutlined /> : <VisibilityOutlined />}
              </IconButton>
            </InputAdornment>
          ),
        }}
      />
    </Box>
  );
}

export default function AuthPage({ onAuthenticated, onNavigate }) {
  const [mode, setMode] = useState("login");
  const [loginType, setLoginType] = useState("user");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [role, setRole] = useState("user");
  const [inviteCode, setInviteCode] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function resetFields() {
    setUsername("");
    setEmail("");
    setPassword("");
    setPasswordConfirmation("");
    setRole("user");
    setInviteCode("");
    setAcceptedTerms(false);
  }

  function switchMode(next) {
    setMode(next);
    setError("");
    setNotice("");
    resetFields();
  }

  async function handleLogin(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const auth = await login(username.trim(), password);
      saveAuth(auth);
      onAuthenticated(auth.user);
      onNavigate(auth.user.role === "admin" ? "admin" : "chat");
    } catch (authError) {
      setError(authError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRegister(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    if (password !== passwordConfirmation) {
      setError("Passwords do not match.");
      return;
    }
    if (!acceptedTerms) {
      setError("Confirm that you agree to the acceptable use notice.");
      return;
    }
    setBusy(true);
    try {
      await register({
        username: username.trim(),
        email: email.trim(),
        password,
        passwordConfirmation,
        role,
        inviteCode: role === "admin" ? inviteCode : undefined,
      });
      const registeredUsername = username.trim();
      switchMode("login");
      setUsername(registeredUsername);
      setNotice(`Account “${registeredUsername}” created. You can now log in.`);
    } catch (registrationError) {
      setError(registrationError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box component="section" sx={{ py: { xs: 3, md: 5 }, px: { xs: 1.5, sm: 3 } }}>
      <Card
        sx={{
          width: "100%",
          maxWidth: mode === "login" ? 520 : 720,
          mx: "auto",
          overflow: "hidden",
          border: "1px solid #dde4df",
          boxShadow: "0 18px 55px rgba(24,60,51,0.11)",
          transition: "max-width 180ms ease",
        }}
      >
        <Box sx={{ p: { xs: 3, sm: 4.5 } }}>
          <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 1, mb: 1 }}>
            {mode === "login" ? <LockOutlined color="primary" /> : <AutoAwesomeOutlined color="primary" />}
            <Typography variant="subtitle2">{mode === "login" ? "Welcome back" : "Join the library"}</Typography>
          </Box>
          <Typography variant="h1" align="center" sx={{ fontSize: { xs: 34, sm: 42 } }}>
            {mode === "login" ? "Log in" : "Create your account"}
          </Typography>
          <Typography variant="body2" align="center" sx={{ mt: 1.2, color: "text.secondary" }}>
            {mode === "login"
              ? "Use your unique username to continue."
              : "Enter your email and create credentials for the research workspace."}
          </Typography>

          {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
          {notice && <Alert severity="success" sx={{ mt: 2 }}>{notice}</Alert>}
          {mode === "login" ? (
            <Box component="form" onSubmit={handleLogin} sx={{ mt: 3, display: "grid", gap: 2 }}>
              <ToggleButtonGroup
                value={loginType}
                exclusive
                onChange={(_, next) => next && setLoginType(next)}
                size="small"
                fullWidth
              >
                <ToggleButton value="user">User</ToggleButton>
                <ToggleButton value="admin">Administrator</ToggleButton>
              </ToggleButtonGroup>
              <Box sx={{ display: "grid", gap: 0.5 }}>
                <Label>Username</Label>
                <TextField
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  autoComplete="username"
                  placeholder="name or name@example.com"
                  fullWidth
                  size="small"
                  required
                />
              </Box>
              <PasswordField
                label="Password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                visible={showPassword}
                onToggle={() => setShowPassword((value) => !value)}
              />
              <Button variant="contained" disabled={busy} type="submit" fullWidth size="large">
                {busy ? "Authenticating..." : `Log in as ${loginType === "admin" ? "administrator" : "user"}`}
              </Button>
              <Button variant="outlined" type="button" onClick={() => switchMode("register")} fullWidth>
                Create an account
              </Button>
              <Button variant="text" type="button" onClick={() => onNavigate("library")} fullWidth>
                Browse the public library
              </Button>
            </Box>
          ) : (
            <Box
              component="form"
              onSubmit={handleRegister}
              sx={{
                mt: 3,
                display: "grid",
                gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
                gap: 1.7,
              }}
            >
              <Box sx={{ display: "grid", gap: 0.5, gridColumn: "1 / -1" }}>
                <Label>Email</Label>
                <TextField
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  type="email"
                  autoComplete="email"
                  placeholder="name@example.com"
                  fullWidth
                  size="small"
                  required
                />
              </Box>
              <Box sx={{ display: "grid", gap: 0.5 }}>
                <Label>Username</Label>
                <TextField
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  autoComplete="username"
                  inputProps={{ minLength: 3, maxLength: 80 }}
                  fullWidth
                  size="small"
                  required
                />
              </Box>
              <PasswordField
                label="Password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
                visible={showPassword}
                onToggle={() => setShowPassword((value) => !value)}
              />
              <PasswordField
                label="Confirm password"
                value={passwordConfirmation}
                onChange={(event) => setPasswordConfirmation(event.target.value)}
                autoComplete="new-password"
                visible={showConfirmation}
                onToggle={() => setShowConfirmation((value) => !value)}
              />
              <Box sx={{ display: "grid", gap: 0.5 }}>
                <Label>Account type</Label>
                <FormControl size="small" fullWidth>
                  <Select value={role} onChange={(event) => { setRole(event.target.value); setInviteCode(""); }}>
                    <MenuItem value="user">User (Policy Researcher)</MenuItem>
                    <MenuItem value="admin">Administrator</MenuItem>
                  </Select>
                </FormControl>
              </Box>
              {role === "admin" && (
                <Box sx={{ display: "grid", gap: 0.5, gridColumn: "1 / -1" }}>
                  <Label>Administrator invitation code</Label>
                  <TextField
                    value={inviteCode}
                    onChange={(event) => setInviteCode(event.target.value.trim())}
                    type="password"
                    placeholder="Paste the single-use code from an administrator"
                    fullWidth
                    size="small"
                    required
                  />
                  <Typography variant="caption" color="text.secondary">
                    Invitation codes expire and can only be used once.
                  </Typography>
                </Box>
              )}
              <FormControlLabel
                sx={{ gridColumn: "1 / -1", alignItems: "flex-start" }}
                control={<Checkbox checked={acceptedTerms} onChange={(event) => setAcceptedTerms(event.target.checked)} />}
                label={<Typography variant="body2">I will use the workspace responsibly and verify important source claims.</Typography>}
              />
              <Button variant="contained" disabled={busy} type="submit" fullWidth size="large" sx={{ bgcolor: GREEN, gridColumn: "1 / -1" }}>
                {busy ? "Creating account..." : "Create account"}
              </Button>
              <Button variant="text" type="button" onClick={() => switchMode("login")} fullWidth sx={{ gridColumn: "1 / -1" }}>
                Already have an account? Log in
              </Button>
            </Box>
          )}
        </Box>
      </Card>
    </Box>
  );
}
