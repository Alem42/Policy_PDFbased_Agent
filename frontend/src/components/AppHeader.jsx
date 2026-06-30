import { Box, Button, Typography } from "@mui/material";
import CircleIcon from "@mui/icons-material/Circle";
import AppMenu from "./AppMenu";

export default function AppHeader({ currentView, documentCount, user, onLogout, onNavigate }) {
  return (
    <Box
      component="header"
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
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

      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          px: 1.5,
          py: 1,
          border: "1px solid #d2d8d1",
          borderRadius: "999px",
          backgroundColor: "#fff",
          fontSize: 14,
          whiteSpace: "nowrap",
        }}
      >
        <CircleIcon sx={{ fontSize: 8, color: "#4a9f6f" }} />
        {user
          ? user.role === "admin"
            ? `Admin Workspace — ${documentCount} document${documentCount === 1 ? "" : "s"}`
            : `${user.username}'s Workspace — ${documentCount} document${documentCount === 1 ? "" : "s"}`
          : "Public Workspace"}
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
  );
}
