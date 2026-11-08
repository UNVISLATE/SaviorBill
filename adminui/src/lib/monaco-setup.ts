/**
 * Регистрация воркеров Monaco Editor через стандартный `new URL(...,
 * import.meta.url)` паттерн — работает с Vite/Rolldown "из коробки", без
 * `?worker`-суффикса (который Rolldown не резолвит внутри пакета
 * `monaco-editor`) и без отдельного vite-plugin-monaco-editor.
 *
 * Импортировать один раз до первого использования `monaco-editor` (см.
 * `LuaEditor.tsx` и `LuaManifestPage.tsx`).
 */
import editorWorkerUrl from "monaco-editor/editor/editor.worker.js?url"
import jsonWorkerUrl from "monaco-editor/language/json/json.worker.js?url"

declare global {
  interface Window {
    MonacoEnvironment?: {
      getWorker: (moduleId: string, label: string) => Worker
    }
  }
}

let configured = false

export function ensureMonacoWorkers(): void {
  if (configured) return
  configured = true
  self.MonacoEnvironment = {
    getWorker(_moduleId: string, label: string) {
      if (label === "json") {
        return new Worker(jsonWorkerUrl, { type: "module" })
      }
      return new Worker(editorWorkerUrl, { type: "module" })
    },
  }
}
