/**
 * Регистрация воркеров Monaco Editor через стандартный `new URL(...,
 * import.meta.url)` паттерн — работает с Vite/Rolldown "из коробки", без
 * `?worker`-суффикса (который Rolldown не резолвит внутри пакета
 * `monaco-editor`) и без отдельного vite-plugin-monaco-editor.
 *
 * Импортировать один раз до первого использования `monaco-editor` (см.
 * `LuaEditor.tsx`).
 */
import editorWorkerUrl from "monaco-editor/editor/editor.worker.js?url"

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
    // Lua не требует отдельного языкового воркера (нет встроенного
    // language-service, только TextMate-подобная подсветка синтаксиса) —
    // всем языкам без спец-воркера достаточно базового editor.worker.
    getWorker(_moduleId: string, _label: string) {
      return new Worker(editorWorkerUrl, { type: "module" })
    },
  }
}
