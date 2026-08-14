import { useCallback, useEffect, useRef, useState } from "react"
import * as monaco from "monaco-editor"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { History } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail, getErrorStatus } from "@/lib/api-error.ts"
import { ensureMonacoWorkers } from "@/lib/monaco-setup"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Textarea } from "@/components/shadsnui/textarea"
import { Badge } from "@/components/shadsnui/badge"
import { Separator } from "@/components/shadsnui/separator"
import { Skeleton } from "@/components/shadsnui/skeleton"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/shadsnui/sheet"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/shadsnui/alert-dialog"

export interface LuaScriptVersion {
  version: number
  sha256: string | null
  commit_message: string | null
  created_at: string
  created_by: number | null
}

export interface LuaScriptVersionDetail extends LuaScriptVersion {
  code: string
}

export interface LuaEditorProps {
  scriptId: number
  initialCode: string
  /** Текущая версия скрипта (для подсветки в списке версий). */
  currentVersion: number
  /** Счётчик оптимистичной блокировки — присылается назад при PATCH/activate;
   * расхождение с сервером даёт 409 (кто-то другой сохранил раньше). */
  lockVersion: number
  /** Есть ли у текущего пользователя право редактировать (lua.edit). */
  canEdit: boolean
  /** Есть ли у текущего пользователя право на sandboxed test-run (lua.test). */
  canTest: boolean
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
 * Редактор Lua-скрипта: Monaco-editor (lua, vs-dark) + панель версий
 * (реальная серверная история, см. Ф3 — `GET /admin/lua/{id}/versions`),
 * diff с любой прошлой версией, откат (`activate`, без создания нового
 * файла), Lint и sandboxed Test-run.
 *
 * Раньше версии жили только в localStorage браузера — серверный API версий
 * (миграция 0008, потом Ф3) не использовался вообще (см. PLAN.md Ф6).
 */
export function LuaEditor({
  scriptId,
  initialCode,
  currentVersion,
  lockVersion,
  canEdit,
  canTest,
}: LuaEditorProps) {
  const qc = useQueryClient()
  const editorHostRef = useRef<HTMLDivElement>(null)
  const diffHostRef = useRef<HTMLDivElement>(null)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const diffEditorRef = useRef<monaco.editor.IStandaloneDiffEditor | null>(null)

  const [diffAgainst, setDiffAgainst] = useState<number | null>(null)
  const [commitMessage, setCommitMessage] = useState("")
  const [dirty, setDirty] = useState(false)
  const [ready, setReady] = useState(false)
  const [conflict, setConflict] = useState(false)
  const [activateTarget, setActivateTarget] = useState<number | null>(null)
  const [lintResult, setLintResult] = useState<{ ok: boolean; error?: string | null } | null>(null)
  const [testRunOpen, setTestRunOpen] = useState(false)
  const [testCtx, setTestCtx] = useState("{}")
  const [testResult, setTestResult] = useState<{
    public: unknown
    private: unknown
    logs: unknown[]
    error?: string | null
  } | null>(null)
  const [versionsSheetOpen, setVersionsSheetOpen] = useState(false)

  const { data: versions } = useQuery({
    queryKey: ["admin-lua-versions", scriptId],
    queryFn: async () =>
      (await api.get<LuaScriptVersion[]>(`/v1/admin/lua/${scriptId}/versions`)).data,
  })

  const { data: diffCode } = useQuery({
    queryKey: ["admin-lua-version-code", scriptId, diffAgainst],
    queryFn: async () =>
      (
        await api.get<LuaScriptVersionDetail>(
          `/v1/admin/lua/${scriptId}/versions/${diffAgainst}`,
        )
      ).data.code,
    enabled: diffAgainst !== null,
  })

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
    if (diffAgainst === null || diffCode === undefined || !diffHostRef.current || !editorRef.current) return

    const originalModel = monaco.editor.createModel(diffCode, "lua")
    const modifiedModel = monaco.editor.createModel(editorRef.current.getValue(), "lua")

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
  }, [diffAgainst, diffCode])

  const save = useMutation({
    mutationFn: async () => {
      const editor = editorRef.current
      if (!editor) throw new Error("editor not ready")
      const code = editor.getValue()
      return (
        await api.patch(`/v1/admin/lua/${scriptId}`, {
          code,
          commit_message: commitMessage.trim() || undefined,
          lock_version: lockVersion,
        })
      ).data
    },
    onSuccess: () => {
      setCommitMessage("")
      setDirty(false)
      setConflict(false)
      toastSuccess("Новая версия скрипта сохранена")
      void qc.invalidateQueries({ queryKey: ["admin-lua-script", scriptId] })
      void qc.invalidateQueries({ queryKey: ["admin-lua-scripts"] })
      void qc.invalidateQueries({ queryKey: ["admin-lua-versions", scriptId] })
    },
    onError: (err: unknown) => {
      if (getErrorStatus(err) === 409) {
        setConflict(true)
        toastError(
          "Скрипт изменили в другой вкладке/другим админом",
          "Обновите страницу, чтобы не потерять чужие правки.",
        )
        return
      }
      toastError("Не удалось сохранить скрипт", getErrorDetail(err))
    },
  })

  // Ctrl+S — сохранить (та же логика, что и кнопка). Отдельный эффект с
  // актуальными canEdit/dirty/save в зависимостях (переустанавливается при
  // их смене) — без ref-хака "последний коллбэк": мутация ref вне
  // рендера/эффекта создания редактора запрещена линтером проекта (см.
  // react-hooks/immutability).
  useEffect(() => {
    const editor = editorRef.current
    if (!editor) return
    const sub = editor.onKeyDown((e) => {
      if ((e.ctrlKey || e.metaKey) && e.keyCode === monaco.KeyCode.KeyS) {
        e.preventDefault()
        if (canEdit && dirty && !save.isPending) save.mutate()
      }
    })
    return () => sub.dispose()
  }, [canEdit, dirty, save, ready])

  const activate = useMutation({
    mutationFn: async (version: number) =>
      (
        await api.post(`/v1/admin/lua/${scriptId}/versions/${version}/activate`, {
          lock_version: lockVersion,
        })
      ).data,
    onSuccess: (_data, version) => {
      toastSuccess(`Версия №${version} стала активной`)
      setActivateTarget(null)
      setDiffAgainst(null)
      void qc.invalidateQueries({ queryKey: ["admin-lua-script", scriptId] })
      void qc.invalidateQueries({ queryKey: ["admin-lua-scripts"] })
      void qc.invalidateQueries({ queryKey: ["admin-lua-versions", scriptId] })
    },
    onError: (err: unknown) => {
      if (getErrorStatus(err) === 409) {
        setConflict(true)
        toastError("Скрипт изменили в другой вкладке/другим админом", "Обновите страницу.")
        return
      }
      toastError("Не удалось активировать версию", getErrorDetail(err))
    },
  })

  const lint = useMutation({
    mutationFn: async () => {
      const editor = editorRef.current
      if (!editor) throw new Error("editor not ready")
      return (await api.post<{ ok: boolean; error?: string | null }>("/v1/admin/lua/lint", { code: editor.getValue() })).data
    },
    onSuccess: (data) => {
      setLintResult(data)
      if (data.ok) toastSuccess("Скрипт компилируется без ошибок")
      else toastError("Ошибка в скрипте", data.error ?? undefined)
    },
    onError: (err: unknown) => toastError("Не удалось проверить скрипт", getErrorDetail(err)),
  })

  const testRun = useMutation({
    mutationFn: async () => {
      const editor = editorRef.current
      if (!editor) throw new Error("editor not ready")
      let ctx: unknown
      try {
        ctx = JSON.parse(testCtx || "{}")
      } catch {
        throw new Error("ctx должен быть валидным JSON")
      }
      return (
        await api.post(`/v1/admin/lua/${scriptId}/test-run`, {
          code: editor.getValue(),
          ctx,
        })
      ).data
    },
    onSuccess: (data) => {
      setTestResult(data)
      if (data.error) toastError("Test-run завершился ошибкой", data.error)
      else toastSuccess("Test-run выполнен (песочница — без реальных http/billing)")
    },
    onError: (err: unknown) =>
      toastError(
        "Не удалось выполнить test-run",
        err instanceof Error && err.message === "ctx должен быть валидным JSON"
          ? err.message
          : getErrorDetail(err),
      ),
  })

  const refreshVersions = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["admin-lua-versions", scriptId] })
  }, [qc, scriptId])

  const versionsList = (
    <>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Версии</h3>
        <Button size="sm" variant="ghost" onClick={refreshVersions}>
          Обновить
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Сохранение без правок не создаёт новую версию.
      </p>
      <div className="flex-1 space-y-1.5 overflow-y-auto pr-1">
        {!versions && (
          <div className="space-y-1.5">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        )}
        {versions?.length === 0 && (
          <p className="rounded-md border border-dashed p-3 text-center text-xs text-muted-foreground">
            Пока нет сохранённых версий
          </p>
        )}
        {versions?.map((v) => (
          <div key={v.version} className="space-y-1.5 rounded-md border p-2.5 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">
                №{v.version}
                {v.version === currentVersion && (
                  <Badge variant="secondary" className="ml-1.5 text-[10px]">активна</Badge>
                )}
              </span>
              <span className="text-xs text-muted-foreground">{formatDateTime(v.created_at)}</span>
            </div>
            {v.commit_message && (
              <p className="line-clamp-2 text-xs text-muted-foreground">{v.commit_message}</p>
            )}
            <div className="flex gap-1.5">
              <Button
                size="sm"
                variant="outline"
                className="h-7 flex-1 px-2 text-xs"
                onClick={() => {
                  setDiffAgainst(v.version)
                  setVersionsSheetOpen(false)
                }}
              >
                Diff
              </Button>
              {canEdit && v.version !== currentVersion && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 flex-1 px-2 text-xs"
                  onClick={() => {
                    setActivateTarget(v.version)
                    setVersionsSheetOpen(false)
                  }}
                >
                  Активировать
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  )

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 md:flex-row">
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">Lua</Badge>
            <Badge variant="outline">v{currentVersion}</Badge>
            {dirty && <Badge variant="secondary">не сохранено</Badge>}
            {conflict && <Badge variant="destructive">конфликт версий — обновите страницу</Badge>}
            {diffAgainst !== null && (
              <Badge variant="secondary">сравнение с версией №{diffAgainst}</Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            {canTest && (
              <Button size="sm" variant="outline" onClick={() => setTestRunOpen((v) => !v)}>
                Test-run
              </Button>
            )}
            {canEdit && (
              <Button size="sm" variant="outline" disabled={lint.isPending} onClick={() => lint.mutate()}>
                {lint.isPending ? "Проверка…" : "Lint"}
              </Button>
            )}
            {diffAgainst !== null && (
              <Button size="sm" variant="outline" onClick={() => setDiffAgainst(null)}>
                Закрыть diff
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              className="md:hidden"
              onClick={() => setVersionsSheetOpen(true)}
            >
              <History className="size-4" /> Версии
            </Button>
          </div>
        </div>

        {lintResult && (
          <div
            className={
              "rounded-md border px-3 py-2 text-xs " +
              (lintResult.ok
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600"
                : "border-destructive/30 bg-destructive/10 text-destructive")
            }
          >
            {lintResult.ok ? "Компилируется без ошибок." : lintResult.error}
          </div>
        )}

        {testRunOpen && (
          <div className="space-y-2 rounded-md border p-3">
            <label className="text-xs font-medium text-muted-foreground">
              ctx (JSON) — передаётся в handle(ctx) в песочнице (http/billing заглушены)
            </label>
            <Textarea
              value={testCtx}
              onChange={(e) => setTestCtx(e.target.value)}
              rows={3}
              className="font-mono text-xs"
            />
            <Button size="sm" disabled={testRun.isPending} onClick={() => testRun.mutate()}>
              {testRun.isPending ? "Выполняется…" : "Запустить"}
            </Button>
            {testResult && (
              <pre className="max-h-40 overflow-auto rounded-md bg-muted/60 p-2 text-xs">
                {JSON.stringify(testResult, null, 2)}
              </pre>
            )}
          </div>
        )}

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
            style={{ display: diffAgainst !== null ? "none" : "block" }}
          />
          <div
            ref={diffHostRef}
            className="h-full w-full"
            style={{ display: diffAgainst !== null ? "block" : "none" }}
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
                disabled={save.isPending}
              />
            </div>
            <Button onClick={() => save.mutate()} disabled={save.isPending || !dirty}>
              {save.isPending ? "Сохранение…" : "Сохранить версию (Ctrl+S)"}
            </Button>
          </div>
        )}
      </div>

      <Separator orientation="vertical" className="hidden h-full md:block" />

      {/* Десктоп — постоянная колонка справа. */}
      <div className="hidden w-72 shrink-0 flex-col gap-2 md:flex">
        {versionsList}
      </div>

      {/* Мобильный — та же панель, но во всплывающей шторке по кнопке
          "Версии" в тулбаре (см. PLAN.md Ф6: три resizable-панели на
          десктопе, Sheet на мобильном — здесь панель одна, но принцип тот же:
          не занимать драгоценную ширину экрана постоянно). */}
      <Sheet open={versionsSheetOpen} onOpenChange={setVersionsSheetOpen}>
        <SheetContent side="right" className="w-[85vw] max-w-sm">
          <SheetHeader>
            <SheetTitle>Версии</SheetTitle>
          </SheetHeader>
          <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden px-4 pb-4">
            {versionsList}
          </div>
        </SheetContent>
      </Sheet>

      <AlertDialog open={activateTarget !== null} onOpenChange={(v) => !v && setActivateTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Активировать версию №{activateTarget}?</AlertDialogTitle>
            <AlertDialogDescription>
              Скрипт начнёт исполняться версией №{activateTarget} немедленно —
              без создания нового файла (откат к уже сохранённому снимку).
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              disabled={activate.isPending}
              onClick={() => activateTarget !== null && activate.mutate(activateTarget)}
            >
              Активировать
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
