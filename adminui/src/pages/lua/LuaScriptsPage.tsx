import { useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { LuaEditor } from "@/components/lua/LuaEditor"
import { Badge } from "@/components/shadsnui/badge"
import { Skeleton } from "@/components/shadsnui/skeleton"
import { Input } from "@/components/shadsnui/input"

interface LuaScript {
  id: number
  slug: string
  name: string | null
  kind: string
  filename: string
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

/** Страница управления Lua-скриптами: список слева, редактор с версиями справа. */
export function LuaScriptsPage() {
  const { can } = useAuth()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [search, setSearch] = useState("")

  const canRead = can("lua.read")
  const canEdit = can("lua.edit")
  const canTest = can("lua.test")

  const { data: scripts, isLoading: scriptsLoading } = useQuery({
    queryKey: ["admin-lua-scripts"],
    queryFn: async () => (await api.get<LuaScript[]>("/v1/admin/lua")).data,
    enabled: canRead,
  })

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["admin-lua-script", selectedId],
    queryFn: async () =>
      (await api.get<LuaScriptDetail>(`/v1/admin/lua/${selectedId}`)).data,
    enabled: canRead && selectedId !== null,
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

  return (
    <div className="flex h-[calc(100vh-8rem)] min-h-0 flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Lua-скрипты</h1>
        {scripts && (
          <span className="text-sm text-muted-foreground">
            Всего: {scripts.length}
          </span>
        )}
      </div>

      <div className="flex min-h-0 flex-1 gap-4">
        <div className="flex w-64 shrink-0 flex-col gap-2">
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
              <button
                key={s.id}
                type="button"
                onClick={() => setSelectedId(s.id)}
                className={
                  "flex w-full flex-col gap-0.5 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors " +
                  (s.id === selectedId
                    ? "bg-primary/10 text-foreground"
                    : "hover:bg-muted/60")
                }
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium">
                    {s.name ?? s.slug}
                  </span>
                  {!s.is_active && (
                    <Badge variant="outline" className="shrink-0 text-[10px]">
                      выключен
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className="truncate">{s.slug}</span>
                  <span>·</span>
                  <span>{s.kind}</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="min-w-0 flex-1 rounded-md border p-3">
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
          {selectedId !== null && detail && (
            <LuaEditor
              // Смена key при выборе другого скрипта пересоздаёт Monaco-
              // редактор с новым initialCode — проще и надёжнее, чем
              // синхронизировать содержимое существующей модели вручную.
              key={detail.id}
              scriptId={detail.id}
              initialCode={detail.code}
              currentVersion={detail.current_version}
              lockVersion={detail.lock_version}
              canEdit={canEdit}
              canTest={canTest}
            />
          )}
        </div>
      </div>
    </div>
  )
}
