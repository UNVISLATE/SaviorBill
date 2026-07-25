import { useCallback, useEffect, useRef, useState } from "react"
import * as monaco from "monaco-editor"

import { ensureMonacoWorkers } from "@/lib/monaco-setup"
import {
  clearVersions,
  listVersions,
  pushVersion,
  type LuaScriptVersion,
} from "@/components/lua/LuaScriptVersions"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Badge } from "@/components/shadsnui/badge"
import { Separator } from "@/components/shadsnui/separator"
import { Skeleton } from "@/components/shadsnui/skeleton"
import { toastError, toastSuccess } from "@/lib/toast"

export interface LuaEditorProps {
  /** id скрипта — используется как ключ версионирования и для сабмита. */
  scriptId: number
  /** Текущий код скрипта, загруженный с сервера (см. GET /admin/lua/{id}). */
  initialCode: string
  /** Логин текущего админа — пишется в запись версии как автор (может быть null). */
  authorLogin: string | null
  /** Есть ли у текущего пользователя право редактировать (lua.edit). */
  canEdit: boolean
  /**
   * Сохранить новую версию кода на сервере (PATCH /admin/lua/{id}).
   * Бросает исключение при ошибке — компонент сам покажет toast и не будет
   * считать версию сохранённой (localStorage не обновится).
   */
  onSave: (code: string) => Promise<void>
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

/**
 * Редактор Lua-скрипта: Monaco-editor (lua, vs-dark) + панель версий с
 * diff-сравнением текущего кода с любой прошлой версией + коммит-сообщение
 * при сохранении.
 *
 * Версии хранятся на клиенте (см. `LuaScriptVersions.ts`) — сервер сейчас
 * хранит только последний код скрипта, без истории.
 */
export function LuaEditor({
  scriptId,
  initialCode,
  authorLogin,
  canEdit,
  onSave,
}: LuaEditorProps) {
  const editorHostRef = useRef<HTMLDivElement>(null)
  const diffHostRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const diffEditorRef = useRef<monaco.editor.IStandaloneDiffEditor | null>(null)

  const [versions, setVersions] = useState<LuaScriptVersion[]>(() =>
    listVersions(scriptId),
  )
  const [diffAgainst, setDiffAgainst] = useState<LuaScriptVersion | null>(null)
  const [commitMessage, setCommitMessage] = useState("")
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [ready, setReady] = useState(false)

  // Инициализация редактора — один раз на маунт компонента.
  useEffect(() => {
    ensureMonacoWorkers()
    if (!editorHostRef.current) return

    const editor = monaco.editor.create(editorHostRef.current, {
      value: initialCode,
      language: "lua",
      theme: "vs-dark",
      automaticLayout: true,
      minimap: { enabled: true },
      fontSize: 13,
      readOnly: !canEdit,
      scrollBeyondLastLine: false,
      tabSize: 2,
    })
    editorRef.current = editor
    setReady(true)

    const sub = editor.onDidChangeModelContent(() => {
      setDirty(editor.getValue() !== initialCode)
    })

    return () => {
      sub.dispose()
      editor.dispose()
      editorRef.current = null
    }
    // initialCode/canEdit намеренно не в deps — переинициализация редактора
    // при смене выбранного скрипта делается через смену `key` на уровне
    // родителя (LuaScriptsPage), а не здесь.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Diff-редактор — создаётся лениво, когда выбрана версия для сравнения.
  useEffect(() => {
    if (!diffAgainst || !diffHostRef.current || !editorRef.current) return

    const originalModel = monaco.editor.createModel(
      diffAgainst.code,
      "lua",
    )
    const modifiedModel = monaco.editor.createModel(
      editorRef.current.getValue(),
      "lua",
    )

    const diffEditor = monaco.editor.createDiffEditor(diffHostRef.current, {
      theme: "vs-dark",
      automaticLayout: true,
      readOnly: true,
      renderSideBySide: true,
      fontSize: 13,
    })
    diffEditor.setModel({ original: originalModel, modified: modifiedModel })
    diffEditorRef.current = diffEditor

    return () => {
      diffEditor.dispose()
      originalModel.dispose()
      modifiedModel.dispose()
      diffEditorRef.current = null
    }
  }, [diffAgainst])

  const refreshVersions = useCallback(() => {
    setVersions(listVersions(scriptId))
  }, [scriptId])

  async function handleSave() {
    const editor = editorRef.current
    if (!editor) return
    const code = editor.getValue()
    if (!code.trim()) {
      toastError("Код скрипта не может быть пустым")
      return
    }
    if (!commitMessage.trim()) {
      toastError("Укажите описание изменений (commit message)")
      return
    }
    setSaving(true)
    try {
      await onSave(code)
      pushVersion(scriptId, code, commitMessage, authorLogin)
      refreshVersions()
      setCommitMessage("")
      setDirty(false)
      toastSuccess("Новая версия скрипта сохранена")
    } catch (err) {
      toastError(
        "Не удалось сохранить скрипт",
        err instanceof Error ? err.message : undefined,
      )
    } finally {
      setSaving(false)
    }
  }

  function handleRestore(version: LuaScriptVersion) {
    const editor = editorRef.current
    if (!editor) return
    editor.setValue(version.code)
    setDirty(true)
    setDiffAgainst(null)
    setCommitMessage(`Откат к версии №${version.version}`)
  }

  function handleClearHistory() {
    clearVersions(scriptId)
    refreshVersions()
    setDiffAgainst(null)
    toastSuccess("Локальная история версий очищена")
  }

  return (
    <div className="flex h-full min-h-0 gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Badge variant="outline">Lua</Badge>
            {dirty && <Badge variant="secondary">не сохранено</Badge>}
            {diffAgainst && (
              <Badge variant="secondary">
                сравнение с версией №{diffAgainst.version}
              </Badge>
            )}
          </div>
          {diffAgainst && (
            <Button size="sm" variant="outline" onClick={() => setDiffAgainst(null)}>
              Закрыть diff
            </Button>
          )}
        </div>

        <div className="relative min-h-0 flex-1 overflow-hidden rounded-md border">
          {!ready && (
            <div className="absolute inset-0 z-10 bg-background">
              <Skeleton className="h-full w-full" />
            </div>
          )}
          {/* Оба хоста существуют всегда — просто скрываем неактивный,
              чтобы не терять состояние/выделение основного редактора при
              открытии diff-режима. */}
          <div
            ref={editorHostRef}
            className="h-full w-full"
            style={{ display: diffAgainst ? "none" : "block" }}
          />
          <div
            ref={diffHostRef}
            className="h-full w-full"
            style={{ display: diffAgainst ? "block" : "none" }}
          />
        </div>

        {canEdit && (
          <div className="flex items-end gap-2">
            <div className="flex-1 space-y-1">
              <label className="text-xs font-medium text-muted-foreground">
                Описание изменений (commit message)
              </label>
              <Input
                value={commitMessage}
                onChange={(e) => setCommitMessage(e.target.value)}
                placeholder="например, исправлена обработка ошибки таймаута"
                disabled={saving}
              />
            </div>
            <Button onClick={handleSave} disabled={saving || !dirty}>
              {saving ? "Сохранение…" : "Сохранить версию"}
            </Button>
          </div>
        )}
      </div>

      <Separator orientation="vertical" className="h-full" />

      <div className="flex w-72 shrink-0 flex-col gap-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Версии</h3>
          {versions.length > 0 && (
            <Button size="sm" variant="ghost" onClick={handleClearHistory}>
              Очистить
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          Локальная история (в этом браузере) — сервер хранит только
          последний код.
        </p>
        <div className="flex-1 space-y-1.5 overflow-y-auto pr-1">
          {versions.length === 0 && (
            <p className="rounded-md border border-dashed p-3 text-center text-xs text-muted-foreground">
              Пока нет сохранённых версий
            </p>
          )}
          {versions.map((v) => (
            <div
              key={v.version}
              className="space-y-1.5 rounded-md border p-2.5 text-sm"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">№{v.version}</span>
                <span className="text-xs text-muted-foreground">
                  {formatDateTime(v.createdAt)}
                </span>
              </div>
              <p className="line-clamp-2 text-xs text-muted-foreground">
                {v.message}
              </p>
              {v.authorLogin && (
                <p className="text-xs text-muted-foreground">
                  автор: {v.authorLogin}
                </p>
              )}
              <div className="flex gap-1.5">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 flex-1 px-2 text-xs"
                  onClick={() => setDiffAgainst(v)}
                >
                  Diff
                </Button>
                {canEdit && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 flex-1 px-2 text-xs"
                    onClick={() => handleRestore(v)}
                  >
                    Восстановить
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
