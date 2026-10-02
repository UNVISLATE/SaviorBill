import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "react-router-dom"
import { ArrowLeft, MoreVertical, Plus, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { useIsMobile } from "@/hooks/use-mobile"
import { useBreadcrumbExtra } from "@/hooks/use-breadcrumb"
import { toastError, toastSuccess } from "@/lib/toast"
import { cn } from "@/lib/utils"
import { LuaEditor } from "@/components/lua/LuaEditor"
import { CreateLuaScriptDialog } from "@/components/lua/CreateLuaScriptDialog"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Skeleton } from "@/components/shadsnui/skeleton"
import { Input } from "@/components/shadsnui/input"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/shadsnui/dropdown-menu"
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

interface LuaScript {
  id: number
  slug: string
  name: string | null
  kind: string
  filename: string
  sha256: string | null
  artifact_status: "ready" | "missing" | "corrupt" | "unknown"
  actions: string[]
  settings: Record<string, unknown>
  is_active: boolean
  current_version: number
  lock_version: number
}

interface LuaScriptDetail extends LuaScript {
  code: string
  version: number
}

/**
 * Список скриптов слева, редактор с версиями справа — на десктопе оба видны
 * всегда. Открытый скрипт имеет собственный URL (`/lua/{id}`) — можно дать
 * ссылку, обновить страницу, вернуться кнопкой "Назад" браузера.
 *
 * На мобильном список и редактор — это ДВА разных экрана: список исчезает,
 * как только открыт скрипт (иначе на маленьком экране не помещается ни то,
 * ни другое), и появляется кнопка "Назад к списку".
 */
export function LuaScriptsPage() {
  const { can } = useAuth()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const isMobile = useIsMobile()
  const { scriptId: scriptIdParam } = useParams<{ scriptId?: string }>()
  const selectedId = scriptIdParam ? Number(scriptIdParam) : null
  const [search, setSearch] = useState("")
  const [creating, setCreating] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<LuaScript | null>(null)

  const canRead = can("lua.read")
  const canEdit = can("lua.edit")
  const canTest = can("lua.test")
  const canCreate = can("lua.create")
  const canDelete = can("lua.delete")

  const { data: scripts, isLoading: scriptsLoading } = useQuery({
    queryKey: ["admin-lua-scripts"],
    queryFn: async () => (await api.get<LuaScript[]>("/v1/admin/lua")).data,
    enabled: canRead,
  })

  const {
    data: detail,
    isLoading: detailLoading,
    error: detailError,
  } = useQuery({
    queryKey: ["admin-lua-script", selectedId],
    queryFn: async () =>
      (await api.get<LuaScriptDetail>(`/v1/admin/lua/${selectedId}`)).data,
    enabled: canRead && selectedId !== null,
  })

  // Хлебная крошка получает имя открытого скрипта — /lua сам по себе значит
  // "Скрипты", а конкретный id иначе никак не подписан в цепочке маршрута.
  useBreadcrumbExtra(detail ? detail.name ?? detail.slug : undefined)

  const del = useMutation({
    mutationFn: async (id: number) => api.delete(`/v1/admin/lua/${id}`),
    onSuccess: () => {
      toastSuccess("Скрипт удалён")
      setDeleteTarget(null)
      void qc.invalidateQueries({ queryKey: ["admin-lua-scripts"] })
      if (selectedId === deleteTarget?.id) navigate("/lua")
    },
    onError: (err: unknown) => {
      toastError("Не удалось удалить скрипт", getErrorDetail(err))
    },
  })

  const filtered =
    scripts?.filter((s) => {
      if (!search.trim()) return true
      const q = search.trim().toLowerCase()
      return (
        s.slug.toLowerCase().includes(q) ||
        (s.name ?? "").toLowerCase().includes(q)
      )
    }) ?? []

  if (!canRead) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Недостаточно прав для просмотра Lua-скриптов.
      </div>
    )
  }

  const showList = !isMobile || selectedId === null
  const showEditor = !isMobile || selectedId !== null

  const listPane = (
    <div className="flex w-full shrink-0 flex-col gap-2 md:w-64">
      <div className="flex items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">Lua-скрипты</h1>
        {canCreate && (
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="size-4" /> Создать
          </Button>
        )}
      </div>
      <Input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Поиск по slug/названию…"
      />
      <div className="flex-1 space-y-1 overflow-y-auto rounded-md border p-1.5">
        {scriptsLoading && (
          <div className="space-y-1.5 p-1">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        )}
        {!scriptsLoading && filtered.length === 0 && (
          <p className="p-3 text-center text-xs text-muted-foreground">
            Ничего не найдено
          </p>
        )}
        {filtered.map((s) => (
          <div
            key={s.id}
            className={cn(
              "group flex w-full items-center gap-1 rounded-md px-1 transition-colors",
              s.id === selectedId ? "bg-primary/10" : "hover:bg-muted/60",
            )}
          >
            <button
              type="button"
              onClick={() => navigate(`/lua/${s.id}`)}
              className="flex min-w-0 flex-1 flex-col gap-0.5 px-1.5 py-1.5 text-left text-sm"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium">{s.name ?? s.slug}</span>
                {!s.is_active && (
                  <Badge variant="outline" className="shrink-0 text-[10px]">
                    выключен
                  </Badge>
                )}
                {s.artifact_status !== "ready" && (
                  <Badge variant="destructive" className="shrink-0 text-[10px]">
                    {s.artifact_status === "missing"
                      ? "файл отсутствует"
                      : "файл повреждён"}
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className="truncate">{s.slug}</span>
                <span>·</span>
                <span>{s.kind}</span>
              </div>
            </button>
            {canDelete && (
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7 shrink-0 text-muted-foreground"
                      aria-label={`Дополнительные действия для ${s.name ?? s.slug}`}
                      onClick={(e) => e.stopPropagation()}
                    />
                  }
                >
                  <MoreVertical className="size-3.5" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-max min-w-[200px]">
                  <DropdownMenuItem
                    className="whitespace-nowrap"
                    variant="destructive"
                    onClick={() => setDeleteTarget(s)}
                  >
                    <Trash2 className="size-4" /> Удалить скрипт
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        ))}
      </div>
    </div>
  )

  const editorPane = (
    <div className="min-w-0 flex-1 rounded-md border p-3">
      {isMobile && selectedId !== null && (
        <Button
          size="sm"
          variant="ghost"
          className="mb-2"
          onClick={() => navigate("/lua")}
        >
          <ArrowLeft className="size-4" /> К списку скриптов
        </Button>
      )}
      {selectedId === null && (
        <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
          Выберите скрипт слева
        </div>
      )}
      {selectedId !== null && detailLoading && (
        <div className="h-full space-y-2">
          <Skeleton className="h-8 w-1/3" />
          <Skeleton className="h-full w-full" />
        </div>
      )}
      {selectedId !== null && detailError && (
        <div className="flex h-full items-center justify-center text-sm text-destructive">
          Не удалось прочитать файл скрипта: {getErrorDetail(detailError)}
        </div>
      )}
      {selectedId !== null && detail && (
        <LuaEditor
          // Смена key при выборе другого скрипта пересоздаёт Monaco-
          // редактор с новым initialCode — проще и надёжнее, чем
          // синхронизировать содержимое существующей модели вручную.
          key={detail.id}
          scriptId={detail.id}
          initialCode={detail.code}
          initialSettings={detail.settings}
          currentVersion={detail.current_version}
          lockVersion={detail.lock_version}
          canEdit={canEdit}
          canTest={canTest}
        />
      )}
    </div>
  )

  return (
    <div className="flex h-[calc(100vh-8rem)] min-h-0 flex-col gap-4">
      <div className="flex min-h-0 flex-1 gap-4">
        {showList && listPane}
        {showEditor && editorPane}
      </div>

      <CreateLuaScriptDialog open={creating} onOpenChange={setCreating} />

      <AlertDialog open={!!deleteTarget} onOpenChange={(v) => !v && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить скрипт «{deleteTarget?.slug}»?</AlertDialogTitle>
            <AlertDialogDescription>
              Нельзя удалить, если скрипт сейчас используется какой-либо услугой
              или провайдером — сервер откажет с описанием, где именно.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              disabled={del.isPending}
              onClick={() => deleteTarget && del.mutate(deleteTarget.id)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Удалить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
