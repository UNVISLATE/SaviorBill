import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "react-router-dom"
import { ArrowLeft, MoreVertical, Plus, Sparkles, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { useIsMobile } from "@/hooks/use-mobile"
import { useBreadcrumbExtra } from "@/hooks/use-breadcrumb"
import { toastError, toastSuccess } from "@/lib/toast"
import { cn } from "@/lib/utils"
import { LuaEditor } from "@/components/lua/LuaEditor"
import { CreateLuaScriptDialog } from "@/components/lua/CreateLuaScriptDialog"
import { CreateFromManifestDialog } from "@/components/lua/CreateFromManifestDialog"
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
  const [prefillScript, setPrefillScript] = useState<LuaScript | null>(null)

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
  useBreadcrumbExtra(
    detail ? detail.name ?? detail.slug : selectedId !== null ? `#${selectedId}` : null,
  )

  const remove = useMutation({
    mutationFn: async (id: number) => (await api.delete(`/v1/admin/lua/${id}`)).data,
    onSuccess: (_, deletedId) => {
      toastSuccess("Скрипт удалён")
      void qc.invalidateQueries({ queryKey: ["admin-lua-scripts"] })
      if (selectedId === deletedId) {
        navigate("/lua")
      }
    },
    onError: (e) => toastError("Не удалось удалить скрипт", getErrorDetail(e)),
  })

  const filtered = (scripts ?? []).filter(
    (s) =>
      s.slug.toLowerCase().includes(search.toLowerCase()) ||
      (s.name ?? "").toLowerCase().includes(search.toLowerCase()),
  )

  const showList = !isMobile || selectedId === null
  const showEditor = !isMobile || selectedId !== null

  const listPane = (
    <div className="flex w-full min-w-0 flex-col gap-2 md:w-80 md:shrink-0">
      <div className="flex items-center gap-2">
        <Input
          placeholder="Поиск скриптов..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-8 text-xs"
        />
        {canCreate && (
          <Button
            size="sm"
            onClick={() => setCreating(true)}
            aria-label="Создать новый скрипт"
          >
            <Plus className="size-4" />
          </Button>
        )}
      </div>

      <div className="flex-1 space-y-1 overflow-auto rounded-md border p-1">
        {scriptsLoading && (
          <div className="space-y-2 p-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        )}
        {!scriptsLoading && filtered.length === 0 && (
          <p className="p-4 text-center text-xs text-muted-foreground">
            {search ? "Ничего не найдено" : "Скриптов пока нет"}
          </p>
        )}
        {filtered.map((s) => (
          <div
            key={s.id}
            onClick={() => navigate(`/lua/${s.id}`)}
            className={cn(
              "group flex cursor-pointer items-start justify-between rounded p-2 text-xs hover:bg-accent",
              selectedId === s.id && "bg-accent font-medium",
            )}
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="truncate">{s.name ?? s.slug}</span>
                {!s.is_active && (
                  <Badge variant="outline" className="text-[10px]">
                    выкл
                  </Badge>
                )}
                {s.artifact_status === "missing" && (
                  <Badge variant="destructive" className="text-[10px]">
                    нет файла
                  </Badge>
                )}
                {s.artifact_status === "corrupt" && (
                  <Badge variant="destructive" className="text-[10px]">
                    битый файл
                  </Badge>
                )}
              </div>
              <p className="font-mono text-[10px] text-muted-foreground">{s.slug}</p>
              <div className="mt-1 flex flex-wrap items-center gap-1">
                <Badge variant="secondary" className="text-[10px]">
                  {s.kind}
                </Badge>
                {s.actions.map((a) => (
                  <Badge key={a} variant="outline" className="text-[10px]">
                    {a}
                  </Badge>
                ))}
                {s.artifact_status === "ready" && (Boolean(s.settings?.manifest) || Boolean(s.settings?.prefill) || Boolean(s.settings?.client_order_form)) && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-5 px-1.5 text-[9px] gap-1 text-primary border-primary/30 hover:bg-primary/10 hover:border-primary/60 ml-0.5"
                    onClick={(e) => {
                      e.stopPropagation()
                      setPrefillScript(s)
                    }}
                    title="Создать услугу или шлюз из манифеста"
                  >
                    <Sparkles className="size-2.5" />
                    {s.kind === "payment" ? "Создать шлюз" : "Создать товар"}
                  </Button>
                )}
              </div>
            </div>

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
          key={detail.id}
          scriptId={detail.id}
          scriptKind={detail.kind}
          scriptName={detail.name ?? detail.slug}
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

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(v) => !v && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить скрипт?</AlertDialogTitle>
            <AlertDialogDescription>
              Скрипт &laquo;{deleteTarget?.name ?? deleteTarget?.slug}&raquo; и все его
              версии будут безвозвратно удалены. Если на него завязаны услуги или
              провайдеры, они перестанут работать.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (deleteTarget) remove.mutate(deleteTarget.id)
                setDeleteTarget(null)
              }}
            >
              Удалить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <CreateFromManifestDialog
        open={Boolean(prefillScript)}
        onOpenChange={(open) => !open && setPrefillScript(null)}
        script={prefillScript}
      />
    </div>
  )
}
