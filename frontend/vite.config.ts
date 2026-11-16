import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Two builds from one codebase (same look, same components):
//   the console + product page (default): /api proxied to the box's backend on :8000, nginx in Docker
//   the portal (--mode portal): portal.html -> dist-portal, served by portal/main.py; /api on :8010
export default defineConfig(({ mode }) =>
  mode === "portal"
    ? {
        plugins: [react(), tailwindcss()],
        publicDir: "public-portal", // only the icon: the product page's photos and videos stay out
        build: { outDir: "dist-portal", rollupOptions: { input: "portal.html" } },
        server: { port: 3010, proxy: { "/api": process.env.PORTAL_BACKEND_URL ?? "http://localhost:8010" } },
      }
    : {
        plugins: [react(), tailwindcss()],
        server: {
          port: 3000,
          proxy: {
            "/api": {
              target: process.env.BACKEND_URL ?? "http://localhost:8000",
              rewrite: (path) => path.replace(/^\/api/, ""),
              ws: true, // the live camera view
            },
          },
        },
      },
);
