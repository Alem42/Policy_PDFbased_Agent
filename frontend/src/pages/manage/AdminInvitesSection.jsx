import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  MenuItem,
  Skeleton,
  TextField,
  Typography,
} from "@mui/material";
import { createAdminInvite, getAdminInvites, revokeAdminInvite } from "../../api";

const STATUS_COLOURS = {
  active: "success",
  used: "default",
  expired: "warning",
  revoked: "error",
};

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "—";
}

export default function AdminInvitesSection() {
  const [invites, setInvites] = useState([]);
  const [days, setDays] = useState(7);
  const [newCode, setNewCode] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setInvites(await getAdminInvites());
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate() {
    setBusy(true);
    setError("");
    setNotice("");
    setNewCode("");
    try {
      const created = await createAdminInvite(Number(days));
      setNewCode(created.invite_code);
      setNotice("Invitation created. Copy it now; the full code is not stored and cannot be shown again.");
      await load();
    } catch (createError) {
      setError(createError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleCopy() {
    await navigator.clipboard.writeText(newCode);
    setNotice("Invitation copied. Share it through a secure channel.");
  }

  async function handleRevoke(inviteId) {
    setBusy(true);
    setError("");
    try {
      await revokeAdminInvite(inviteId);
      setNotice("Invitation revoked.");
      await load();
    } catch (revokeError) {
      setError(revokeError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Typography variant="subtitle2">Access control</Typography>
      <Typography variant="h2" sx={{ fontSize: 24, mb: 1 }}>Administrator invitations</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Each code grants one new administrator account. Codes are stored as hashes, expire
        automatically and are consumed atomically during registration.
      </Typography>

      {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Box sx={{ p: 2, border: "1px solid #e2e5df", borderRadius: 2, mb: 2 }}>
        <Typography variant="body2" sx={{ fontWeight: 800, mb: 1 }}>Create an invitation</Typography>
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
          <TextField
            select
            size="small"
            label="Valid for"
            value={days}
            onChange={(event) => setDays(event.target.value)}
            sx={{ width: 150 }}
          >
            {[1, 3, 7, 14, 30].map((value) => (
              <MenuItem key={value} value={value}>{value} day{value === 1 ? "" : "s"}</MenuItem>
            ))}
          </TextField>
          <Button variant="contained" disabled={busy} onClick={handleCreate}>
            Create invitation
          </Button>
        </Box>
        {newCode && (
          <Box sx={{ mt: 2, display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
            <TextField
              value={newCode}
              size="small"
              InputProps={{ readOnly: true }}
              sx={{ minWidth: { xs: "100%", sm: 390 } }}
            />
            <Button variant="outlined" onClick={handleCopy}>Copy</Button>
          </Box>
        )}
      </Box>

      <Typography variant="body2" sx={{ fontWeight: 800, mb: 1 }}>Invitation history</Typography>
      {loading ? (
        <Skeleton variant="rounded" height={160} />
      ) : invites.length === 0 ? (
        <Typography variant="body2" color="text.secondary">No invitations have been created.</Typography>
      ) : (
        <Box sx={{ display: "grid", gap: 1 }}>
          {invites.map((invite) => (
            <Box
              key={invite.id}
              sx={{ p: 1.5, border: "1px solid #e2e5df", borderRadius: 2, display: "flex", gap: 2, alignItems: "center", flexWrap: "wrap" }}
            >
              <Box sx={{ minWidth: 110 }}>
                <Typography variant="body2" sx={{ fontFamily: "monospace", fontWeight: 800 }}>
                  {invite.code_prefix}…
                </Typography>
                <Chip label={invite.status} color={STATUS_COLOURS[invite.status]} size="small" />
              </Box>
              <Box sx={{ flex: 1, minWidth: 220 }}>
                <Typography variant="caption" display="block">
                  Created by {invite.created_by_username || "system bootstrap"} · {formatDate(invite.created_at)}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block">
                  Expires {formatDate(invite.expires_at)}
                  {invite.consumed_by_username ? ` · Used by ${invite.consumed_by_username}` : ""}
                </Typography>
              </Box>
              {invite.status === "active" && (
                <Button color="error" variant="outlined" size="small" disabled={busy} onClick={() => handleRevoke(invite.id)}>
                  Revoke
                </Button>
              )}
            </Box>
          ))}
        </Box>
      )}
    </>
  );
}
