import path from "path"
import { execSync } from "child_process"
import fs from "fs"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

let gitCommit = process.env.VITE_GIT_COMMIT || process.env.GIT_COMMIT || ""
let gitDate = process.env.VITE_GIT_COMMIT_DATE || process.env.GIT_COMMIT_DATE || ""
if (!gitCommit) {
  try {
    gitCommit = execSync("git rev-parse --short HEAD").toString().trim()
    gitDate = execSync("git log -1 --format=%cd --date=format:%d.%m.%Y").toString().trim()
  } catch {
    // git may not be available in non-git environments
  }
}

let appVersion = process.env.VITE_APP_VERSION || process.env.APP_VERSION || ""
if (!appVersion) {
  try {
    const versionFile = path.resolve(__dirname, "../VERSION")
    if (fs.existsSync(versionFile)) {
      appVersion = fs.readFileSync(versionFile, "utf-8").trim()
    }
  } catch {
    // fallback if file doesn't exist
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __GIT_COMMIT__: JSON.stringify(gitCommit),
    __GIT_COMMIT_DATE__: JSON.stringify(gitDate),
    __APP_VERSION__: JSON.stringify(appVersion),
  },
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
