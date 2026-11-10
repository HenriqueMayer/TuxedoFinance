import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the client runs on its own port and sends /api to Django.
// In production Django serves the built files, so both share one origin.
// The demonstration (`--mode demo`) is static files under any path, so its URLs are relative.
export default defineConfig(({ mode }) => ({
  base: mode === "demo" ? "./" : "/",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
  },
}));
