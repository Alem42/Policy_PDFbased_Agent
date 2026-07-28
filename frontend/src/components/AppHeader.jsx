import { useEffect, useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import CircleIcon from "@mui/icons-material/Circle";
import AppMenu from "./AppMenu";
import { getEmbeddingSettings } from "../api";

export default function AppHeader({ currentView, documentCount, user, onLogout, onNavigate }) {
  const [embedding, setEmbedding] = useState(null);

  // Show the active embedding model to admins. Refetch on view change so it
  // updates after editing it in Manage > Embedding.
  useEffect(() => {
    if (user?.role !== "admin") {
      setEmbedding(null);
      return;
    }
    let active = true;
    getEmbeddingSettings()
      .then((result) => active && setEmbedding(result.status || null))
      .catch(() => active && setEmbedding(null));
    return () => {
      active = false;
    };
  }, [user, currentView]);

  // Refresh the pill immediately when the embedding model is changed in Manage,
  // without needing a page reload or navigation.
  useEffect(() => {
    if (user?.role !== "admin") return undefined;
    function refetch() {
      getEmbeddingSettings()
        .then((result) => setEmbedding(result.status || null))
        .catch(() => {});
    }
    window.addEventListener("embedding-config-changed", refetch);
    return () => window.removeEventListener("embedding-config-changed", refetch);
  }, [user]);

  const isAdmin = user?.role === "admin";
  const workspaceLabel = user
    ? isAdmin
      ? "Admin Workspace"
      : `${user.username}'s Workspace`
    : "Public Workspace";

  return (
    <Box
      component="header"
      sx={{
        display: "flex",
        alignItems: "center",
        gap: "18px",
        py: "22px",
        borderBottom: "1px solid #d9d8d0",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: "14px" }}>
        <AppMenu currentView={currentView} user={user} onNavigate={onNavigate} />
        <Button
          onClick={() => onNavigate("chat")}
          sx={{
            display: "flex",
            alignItems: "center",
            gap: "12px",
            p: 0,
            border: 0,
            color: "text.primary",
            backgroundColor: "transparent",
            textAlign: "left",
            textTransform: "none",
            "&:hover": { backgroundColor: "transparent" },
          }}
        >
          <Box
            sx={{
              display: "grid",
              width: 42,
              height: 42,
              placeItems: "center",
              borderRadius: "10px",
              color: "#fff",
              backgroundColor: "#214f42",
              fontFamily: "Georgia, serif",
              fontSize: 23,
            }}
          >
            P
          </Box>
          <Box>
            <Typography component="strong" sx={{ display: "block", fontWeight: 700 }}>
              Policy in Action Library
            </Typography>
            <Typography
              component="small"
              sx={{ display: "block", color: "#64716b", fontSize: 13 }}
            >
              Formulate Policy Like an Expert
            </Typography>
          </Box>
        </Button>
      </Box>

      {/* Right group: one unified status pill + auth button. */}
      <Box sx={{ ml: "auto", display: "flex", alignItems: "center", gap: 1.25 }}>
        <Box
          onClick={isAdmin ? () => onNavigate("manage") : undefined}
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 0.75,
            px: 1.75,
            py: 1,
            border: "1px solid #d2d8d1",
            borderRadius: "999px",
            backgroundColor: "#fff",
            fontSize: 13.5,
            whiteSpace: "nowrap",
            cursor: isAdmin ? "pointer" : "default",
            "&:hover": isAdmin ? { backgroundColor: "#f5f7f4", borderColor: "#c5cac3" } : undefined,
          }}
        >
          <CircleIcon sx={{ fontSize: 8, color: "#4a9f6f" }} />
          <Box component="span" sx={{ fontWeight: 700, color: "#2f3a34" }}>
            {workspaceLabel}
          </Box>
          {user && (
            <Box component="span" sx={{ color: "#64716b" }}>
              · {documentCount} doc{documentCount === 1 ? "" : "s"}
            </Box>
          )}
          {isAdmin && embedding && (
            <Box component="span" sx={{ color: "#214f42", fontWeight: 700 }}>
              · {embedding.model} · {embedding.dimension}d
            </Box>
          )}
        </Box>

        {user ? (
          <Button variant="outlined" onClick={onLogout}>
            {user.username} — Log out
          </Button>
        ) : (
          <Button variant="contained" onClick={() => onNavigate("auth")}>
            Login
          </Button>
        )}
      </Box>
    </Box>
  );
}
