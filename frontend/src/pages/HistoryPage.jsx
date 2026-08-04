import { useEffect, useState, useCallback } from "react";
import {
  Box,
  Typography,
  List,
  ListItemButton,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Divider,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Chip,
  Alert,
  CircularProgress,
  Tooltip,
} from "@mui/material";
import DeleteIcon from "@mui/icons-material/DeleteOutlined";
import EditIcon from "@mui/icons-material/EditOutlined";
import ChatIcon from "@mui/icons-material/ChatOutlined";
import { getChatSessions, deleteChatSession, renameChatSession } from "../api";

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatResponseMode(mode) {
  if (mode === "policymaker") return "Policymaker";
  if (mode === "student") return "Student";
  if (mode === "researcher") return "Policy Researcher";
  return mode;
}

export default function HistoryPage({ onNavigate }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Rename dialog state
  const [renaming, setRenaming] = useState(null); // { id, title }
  const [newTitle, setNewTitle] = useState("");

  // Delete confirmation state
  const [deleting, setDeleting] = useState(null); // session id

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getChatSessions();
      setSessions(data);
    } catch (e) {
      setError(e.message || "Failed to load sessions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleDelete() {
    if (!deleting) return;
    try {
      await deleteChatSession(deleting);
      setSessions((prev) => prev.filter((s) => s.id !== deleting));
    } catch (e) {
      setError(e.message || "Failed to delete session");
    } finally {
      setDeleting(null);
    }
  }

  async function handleRename() {
    if (!renaming || !newTitle.trim()) return;
    try {
      await renameChatSession(renaming.id, newTitle.trim());
      setSessions((prev) =>
        prev.map((s) => (s.id === renaming.id ? { ...s, title: newTitle.trim() } : s)),
      );
    } catch (e) {
      setError(e.message || "Failed to rename session");
    } finally {
      setRenaming(null);
      setNewTitle("");
    }
  }

  function openSession(session) {
    onNavigate("chat", { sessionId: session.id });
  }

  return (
    <Box sx={{ maxWidth: 760, mx: "auto", px: 2, py: 4 }}>
      <Typography variant="h5" fontWeight={700} color="#214f42" gutterBottom>
        Chat History
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Past conversations are saved automatically. Click a session to continue it.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}>
          <CircularProgress size={28} />
        </Box>
      ) : sessions.length === 0 ? (
        <Box sx={{ textAlign: "center", mt: 8, color: "text.secondary" }}>
          <ChatIcon sx={{ fontSize: 48, mb: 1, opacity: 0.3 }} />
          <Typography>No conversations yet. Start a chat to see history here.</Typography>
        </Box>
      ) : (
        <List disablePadding>
          {sessions.map((session, idx) => (
            <Box key={session.id}>
              {idx > 0 && <Divider />}
              <ListItemButton
                onClick={() => openSession(session)}
                sx={{
                  borderRadius: "8px",
                  py: 1.5,
                  "&:hover": { backgroundColor: "#f5f5f0" },
                }}
              >
                <ListItemText
                  primary={
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                      <Typography fontWeight={600} noWrap sx={{ maxWidth: 380 }}>
                        {session.title || "Untitled session"}
                      </Typography>
                      {session.response_mode && (
                        <Chip
                          label={formatResponseMode(session.response_mode)}
                          size="small"
                          sx={{
                            height: 18,
                            fontSize: 10,
                            backgroundColor: "#e8f0ee",
                            color: "#214f42",
                          }}
                        />
                      )}
                    </Box>
                  }
                  secondary={
                    <Box component="span" sx={{ display: "block" }}>
                      {session.last_message_preview && (
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          noWrap
                          sx={{ maxWidth: 400 }}
                        >
                          {session.last_message_preview}
                        </Typography>
                      )}
                      <Typography variant="caption" color="text.disabled">
                        {formatDate(session.updated_at)}
                      </Typography>
                    </Box>
                  }
                />
                <ListItemSecondaryAction>
                  <Tooltip title="Rename">
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        setRenaming({ id: session.id, title: session.title });
                        setNewTitle(session.title || "");
                      }}
                    >
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Delete">
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleting(session.id);
                      }}
                      sx={{ color: "#c62828" }}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </ListItemSecondaryAction>
              </ListItemButton>
            </Box>
          ))}
        </List>
      )}

      {/* Rename dialog */}
      <Dialog open={Boolean(renaming)} onClose={() => setRenaming(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Rename conversation</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            label="Title"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleRename()}
            inputProps={{ maxLength: 200 }}
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRenaming(null)}>Cancel</Button>
          <Button variant="contained" onClick={handleRename} disabled={!newTitle.trim()}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={Boolean(deleting)} onClose={() => setDeleting(null)} maxWidth="xs">
        <DialogTitle>Delete conversation?</DialogTitle>
        <DialogContent>
          <Typography>This will permanently remove the session and all its messages.</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleting(null)}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleDelete}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
