import { StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { router } from "./router";
import theme from "./theme";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Suspense
        fallback={
          <div style={{ padding: "2rem", textAlign: "center" }} role="status">
            Loading page…
          </div>
        }
      >
        <RouterProvider router={router} />
      </Suspense>
    </ThemeProvider>
  </StrictMode>,
);
