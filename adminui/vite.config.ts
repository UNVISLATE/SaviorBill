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
        // Единый префикс /api/*: mediaworker — только /api/media/* (более
        // специфичный путь должен идти первым, иначе перехватит общий /api),
        // всё остальное (/api/v1/*, будущие /api/v2/* и т.п., плюс WS-роуты
        // billing под /apiws/*, который тоже начинается на "/api" — совпадает
        // с этим правилом по префиксу) — billing. WS переопределять отдельно
        // не нужно: ws:true на обоих правилах покрывает и HTTP, и WS без
        // дублирования путей.
        "/api/media": {
          target: "http://127.0.0.1:8001",
          changeOrigin: true,
          ws: true,
        },
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          ws: true,
        },
      },
  },
})
