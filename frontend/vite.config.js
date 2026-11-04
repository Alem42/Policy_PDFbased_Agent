import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // VITE_API_PROXY points the dev server at another backend, e.g. a second instance.
      "/api": process.env.VITE_API_PROXY || "http://127.0.0.1:8000",
    },
  },
});
