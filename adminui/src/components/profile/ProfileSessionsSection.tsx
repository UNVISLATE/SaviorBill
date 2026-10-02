import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Laptop, ShieldOff, Smartphone } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { Skeleton } from "@/components/shadsnui/skeleton"
import { Empty, EmptyDescription, EmptyMedia, EmptyTitle } from "@/components/shadsnui/empty"

interface SessionOut {
  session_id: string
  ip: string | null
  user_agent: string | null
  created_at: string
  last_seen_at: string
  expires_at: string
  is_current: boolean
}

function deviceLabel(ua: string | null): string {
  if (!ua) return "Неизвестное устройство"
  if (/mobile|android|iphone/i.test(ua)) return "Мобильное устройство"
  return "Компьютер"
}

function fmt(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? "Дата неизвестна"
    : date.toLocaleString("ru-RU")
}

/** Активные сессии пользователя — IP + устройство из durable auth state. */
export function ProfileSessionsSection({
  userId,
  mode = "view",
}: {
  userId?: number
  mode?: "own" | "view"
}) {
  const { can } = useAuth()
  const qc = useQueryClient()
  const allowed = mode === "own" || can("admin.user.sessions.manage")
  const basePath = mode === "own" ? "/v1/user/me/sessions" : `/v1/admin/users/${userId}/sessions`

  const { data, isLoading } = useQuery({
    queryKey: [mode === "own" ? "my-sessions" : "admin-user-sessions", userId],
    queryFn: async () =>
      (await api.get<SessionOut[]>(basePath)).data,
    enabled: allowed && (mode === "own" || !!userId),
  })

  const revoke = useMutation({
    mutationFn: async (sessionId: string) =>
      api.delete(`${basePath}/${sessionId}`),
    onSuccess: () => {
      toastSuccess("Сессия завершена")
      void qc.invalidateQueries({ queryKey: [mode === "own" ? "my-sessions" : "admin-user-sessions", userId] })
    },
    onError: () => toastError("Не удалось завершить сессию"),
  })

  const revokeAll = useMutation({
    mutationFn: async () =>
      api.post(mode === "own" ? "/v1/user/me/sessions/revoke-all" : `/v1/admin/users/${userId}/sessions/revoke-all`),
    onSuccess: () => {
      toastSuccess("Все сессии завершены")
      void qc.invalidateQueries({ queryKey: [mode === "own" ? "my-sessions" : "admin-user-sessions", userId] })
    },
    onError: () => toastError("Не удалось завершить все сессии"),
  })

  if (!allowed) {
    return (
      <Empty>
        <EmptyMedia>
          <ShieldOff className="size-8 text-muted-foreground" />
        </EmptyMedia>
        <EmptyTitle>Недостаточно прав</EmptyTitle>
        <EmptyDescription>Нужно право admin.user.sessions.manage.</EmptyDescription>
      </Empty>
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <Empty>
        <EmptyMedia>
          <Laptop className="size-8 text-muted-foreground" />
        </EmptyMedia>
        <EmptyTitle>Нет активных сессий</EmptyTitle>
        <EmptyDescription>Пользователь сейчас не авторизован ни на одном устройстве.</EmptyDescription>
      </Empty>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <Button
          size="sm"
          variant="outline"
          disabled={revokeAll.isPending}
          onClick={() => revokeAll.mutate()}
        >
          Завершить все
        </Button>
      </div>
      {data.map((s) => {
        const isMobile = /mobile|android|iphone/i.test(s.user_agent ?? "")
        return (
          <div
            key={s.session_id}
            className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm"
          >
            <div className="flex min-w-0 items-start gap-2.5">
              {isMobile ? (
                <Smartphone className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              ) : (
                <Laptop className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              )}
              <div className="min-w-0">
                <p className="font-medium">{deviceLabel(s.user_agent)}</p>
                {s.is_current && (
                  <p className="text-xs font-medium text-primary">Текущая сессия</p>
                )}
                <p className="truncate text-xs text-muted-foreground">
                  {s.ip ?? "IP неизвестен"} · вход {fmt(s.created_at)}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  последняя активность: {fmt(s.last_seen_at)}
                </p>
              </div>
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={revoke.isPending}
              onClick={() => revoke.mutate(s.session_id)}
            >
              Завершить
            </Button>
          </div>
        )
      })}
    </div>
  )
}
