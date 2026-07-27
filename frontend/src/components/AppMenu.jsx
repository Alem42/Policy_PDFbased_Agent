import { useState } from "react";
import { Button, Menu, MenuItem, ListItemIcon, ListItemText, Divider } from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import ChatIcon from "@mui/icons-material/ChatOutlined";
import LibraryBooksIcon from "@mui/icons-material/LibraryBooksOutlined";
import DashboardIcon from "@mui/icons-material/DashboardOutlined";
import TuneIcon from "@mui/icons-material/TuneOutlined";
import SettingsIcon from "@mui/icons-material/SettingsOutlined";

const PUBLIC_ITEMS = [
  // { view: "home", label: "Overview", icon: <HomeIcon fontSize="small" /> },
  { view: "chat", label: "Question & Answer", icon: <ChatIcon fontSize="small" /> },
  { view: "library", label: "Document Library", icon: <LibraryBooksIcon fontSize="small" /> },
];

const ADMIN_ITEMS = [
  { view: "admin", label: "Dashboard", icon: <DashboardIcon fontSize="small" /> },
  { view: "manage", label: "Global Management", icon: <TuneIcon fontSize="small" /> },
  { view: "settings", label: "Token Settings", icon: <SettingsIcon fontSize="small" /> },
];

export default function AppMenu({ currentView, user, onNavigate }) {
  const [anchorEl, setAnchorEl] = useState(null);
  const open = Boolean(anchorEl);

  function handleOpen(event) {
    setAnchorEl(event.currentTarget);
  }

  function handleClose() {
    setAnchorEl(null);
  }

  function navigate(view) {
    onNavigate(view);
    handleClose();
  }

  return (
    <>
      <Button
        variant="outlined"
        startIcon={<MenuIcon />}
        aria-label="Open navigation menu"
        aria-controls={open ? "app-nav-menu" : undefined}
        aria-haspopup="true"
        aria-expanded={open ? "true" : undefined}
        onClick={handleOpen}
        sx={{
          borderRadius: "999px",
          borderColor: "#d2d8d1",
          color: "#214f42",
          backgroundColor: "#fff",
          fontWeight: 800,
          height: 42,
          px: 2,
          "&:hover": {
            backgroundColor: "#f5f5f0",
            borderColor: "#c5cac3",
          },
        }}
      >
        Menu
      </Button>
      <Menu
        id="app-nav-menu"
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        MenuListProps={{ "aria-label": "Navigation menu" }}
        slotProps={{
          paper: {
            sx: {
              mt: 1,
              minWidth: 220,
              borderRadius: "10px",
              border: "1px solid #d7d8d0",
              boxShadow: "0 18px 45px rgba(46, 55, 50, 0.18)",
            },
          },
        }}
        transformOrigin={{ horizontal: "left", vertical: "top" }}
        anchorOrigin={{ horizontal: "left", vertical: "bottom" }}
      >
        {PUBLIC_ITEMS.map((item) => (
          <MenuItem
            key={item.view}
            onClick={() => navigate(item.view)}
            selected={currentView === item.view}
            sx={{
              mx: 0.75,
              my: 0.25,
              borderRadius: "8px",
              fontWeight: 750,
            }}
          >
            <ListItemIcon sx={{ minWidth: 36 }}>{item.icon}</ListItemIcon>
            <ListItemText>{item.label}</ListItemText>
          </MenuItem>
        ))}
        {user?.role === "admin" && [
          <Divider key="div" sx={{ my: 0.5 }} />,
          ...ADMIN_ITEMS.map((item) => (
            <MenuItem
              key={item.view}
              onClick={() => navigate(item.view)}
              selected={currentView === item.view}
              sx={{
                mx: 0.75,
                my: 0.25,
                borderRadius: "8px",
                fontWeight: 750,
              }}
            >
              <ListItemIcon sx={{ minWidth: 36 }}>{item.icon}</ListItemIcon>
              <ListItemText>{item.label}</ListItemText>
            </MenuItem>
          )),
        ]}
      </Menu>
    </>
  );
}
