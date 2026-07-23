import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Laptop, ShieldOff, Smartphone } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { Skeleton } from "@/components/shadsnui/skeleton"
import { Empty, EmptyDescription, EmptyMedia, EmptyTitle } from "@/components/shadsnui/empty"

interface SessionOut {
  jti: string
  ip: string | null
  user_agent: string | null
  created_at: number
  last_seen_at: number
  expires_at: number
}

function deviceLabel(ua: string | null): string {
  if (!ua) return "Неизвестное устройство"
  if (/mobile|android|iphone/i.test(ua)) return "Мобильное устройство"
  return "Компьютер"
}

function fmt(unixSec: number): string {
  return new Date(unixSec * 1000).toLocaleString("ru-RU")
}

/** Активные сессии (JWT) пользователя — IP + устройство, из Valkey. Только
 * в чужом (админском) просмотре профиля, требует admin.user.sessions.manage. */
export function ProfileSessionsSection({ userId }: { userId?: number }) {
  const { can } = useAuth()
  const qc = useQueryClient()
  const allowed = can("admin.user.sessions.manage")

  const { data, isLoading } = useQuery({
    queryKey: ["admin-user-sessions", userId],
    queryFn: async () =>
      (await api.get<SessionOut[]>(`/v1/admin/users/${userId}/sessions`)).data,
    enabled: allowed && !!userId,
  })

  const revoke = useMutation({
    mutationFn: async (jti: string) =>
      api.delete(`/v1/admin/users/${userId}/sessions/${jti}`),
    onSuccess: () => {
      toastSuccess("Сессия завершена")
      void qc.invalidateQueries({ queryKey: ["admin-user-sessions", userId] })
    },
    onError: () => toastError("Не удалось завершить сессию"),
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
      {data.map((s) => {
        const isMobile = /mobile|android|iphone/i.test(s.user_agent ?? "")
        return (
          <div
            key={s.jti}
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
              onClick={() => revoke.mutate(s.jti)}
            >
              Завершить
            </Button>
          </div>
        )
      })}
    </div>
  )
}
