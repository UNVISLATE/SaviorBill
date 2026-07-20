import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@/components/ui": path.resolve(__dirname, "./src/components/shadsnui"),
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
      port: 5173,
      host: "127.0.0.1",
      proxy: {
        // billing (main API) отдаёт /api/v1/*; mediaworker — отдельный сервис
        // на своём порту, слушает /api/media/* (без /v1) — см. deploy/Caddyfile,
        // в проде это вообще отдельный домен (MEDIA_DOMAIN). Более специфичный
        // путь должен идти первым, иначе перехватит общий "/api".
        "/api/media": {
          target: "http://127.0.0.1:8001",
          changeOrigin: true,
        },
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
  },
})
