import { createTheme } from "@mui/material/styles";

const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#214f42",
      contrastText: "#fff",
    },
    secondary: {
      main: "#426f5e",
    },
    background: {
      default: "#f4f2ed",
      paper: "#ffffff",
    },
    text: {
      primary: "#17201c",
      secondary: "#64716b",
    },
    divider: "#d9d8d0",
    error: {
      main: "#a13e3e",
      light: "#fff0ef",
    },
    success: {
      main: "#4a9f6f",
    },
  },
  typography: {
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    h1: {
      fontFamily: 'Georgia, "Times New Roman", serif',
      fontWeight: 500,
      fontSize: "clamp(42px, 6vw, 68px)",
      lineHeight: 1,
      letterSpacing: 0,
    },
    h2: {
      fontFamily: 'Georgia, "Times New Roman", serif',
      fontWeight: 500,
      fontSize: "30px",
      lineHeight: 1.12,
      letterSpacing: 0,
    },
    h3: {
      fontFamily: 'Georgia, "Times New Roman", serif',
      fontWeight: 500,
      fontSize: "24px",
    },
    body1: {
      fontSize: "17px",
      lineHeight: 1.6,
    },
    body2: {
      fontSize: "14px",
      lineHeight: 1.5,
    },
    subtitle2: {
      fontSize: "12px",
      fontWeight: 850,
      letterSpacing: "0.14em",
      textTransform: "uppercase",
      color: "#426f5e",
    },
    button: {
      fontWeight: 800,
      textTransform: "none",
    },
  },
  shape: {
    borderRadius: 8,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          margin: 0,
          minWidth: 320,
          minHeight: "100vh",
          backgroundColor: "#f4f2ed",
        },
        "*, *::before, *::after": {
          boxSizing: "border-box",
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          minHeight: 40,
          padding: "9px 14px",
          borderRadius: 8,
          fontWeight: 800,
          textTransform: "none",
          whiteSpace: "nowrap",
        },
        containedPrimary: {
          backgroundColor: "#214f42",
          "&:hover": {
            backgroundColor: "#1a3f35",
          },
        },
        outlined: {
          borderColor: "#d6dbd5",
          color: "#405049",
          backgroundColor: "#fff",
          "&:hover": {
            backgroundColor: "#f5f5f0",
            borderColor: "#c5cac3",
          },
        },
        containedError: {
          backgroundColor: "#fff0ef",
          color: "#a13e3e",
          "&:hover": {
            backgroundColor: "#ffe8e5",
          },
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          "& .MuiOutlinedInput-root": {
            borderRadius: 8,
            backgroundColor: "#fff",
            "& fieldset": {
              borderColor: "#ccd4cd",
            },
          },
        },
      },
    },
    MuiSelect: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          backgroundColor: "#fff",
          "& .MuiOutlinedInput-notchedOutline": {
            borderColor: "#ccd4cd",
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 8,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          border: "1px solid rgba(201, 204, 196, 0.92)",
          borderRadius: 8,
          background: "rgba(255, 255, 255, 0.86)",
          boxShadow: "0 14px 42px rgba(47, 57, 51, 0.06)",
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 6,
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: "transparent",
          boxShadow: "none",
          borderBottom: "1px solid #d9d8d0",
        },
      },
    },
  },
});

export default theme;
