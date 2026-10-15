import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Laptop, ShieldOff, Smartphone, Tv } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { toastError, toastSuccess } from "@/lib/toast"
import { Badge } from "@/components/shadsnui/badge"
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

interface DeviceInfo {
  title: string
  icon: "pc" | "phone" | "tv"
}

export function parseDeviceInfo(ua: string | null): DeviceInfo {
  if (!ua) return { title: "Неизвестное устройство", icon: "pc" }
  const lower = ua.toLowerCase()

  if (
    lower.includes("android tv") ||
    lower.includes("smart-tv") ||
    lower.includes("smarttv") ||
    lower.includes("googletv") ||
    lower.includes("tizen") ||
    lower.includes("webos")
  ) {
    return { title: "Android TV / Smart TV", icon: "tv" }
  }

  if (lower.includes("iphone")) {
    const match = ua.match(/OS (\d+[._]\d+)/)
    const ver = match ? ` iOS ${match[1].replace("_", ".")}` : " iOS"
    return { title: `iPhone (${ver.trim()})`, icon: "phone" }
  }

  if (lower.includes("ipad")) {
    return { title: "iPad (iPadOS)", icon: "phone" }
  }

  if (lower.includes("android")) {
    const match = ua.match(/Android (\d+(\.\d+)?)/)
    const ver = match ? ` ${match[1]}` : ""
    return { title: `Android${ver}`, icon: "phone" }
  }

  if (
    lower.includes("windows nt 10.0") ||
    lower.includes("windows nt 11.0") ||
    lower.includes("windows nt 6.3") ||
    lower.includes("windows")
  ) {
    return { title: "PC (Windows)", icon: "pc" }
  }

  if (lower.includes("macintosh") || lower.includes("mac os x")) {
    return { title: "Mac (macOS)", icon: "pc" }
  }

  if (lower.includes("linux")) {
    return { title: "PC (Linux)", icon: "pc" }
  }

  return { title: "Компьютер", icon: "pc" }
}

function fmt(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? "Дата неизвестна"
    : date.toLocaleString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
}

/** Активные сессии пользователя — подробные устройства, запрет отзыва текущей сессии. */
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
    queryFn: async () => (await api.get<SessionOut[]>(basePath)).data,
    enabled: allowed && (mode === "own" || !!userId),
  })

  const revoke = useMutation({
    mutationFn: async (sessionId: string) => api.delete(`${basePath}/${sessionId}`),
    onSuccess: () => {
      toastSuccess("Сессия завершена")
      void qc.invalidateQueries({
        queryKey: [mode === "own" ? "my-sessions" : "admin-user-sessions", userId],
      })
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
        <Skeleton className="h-16 w-full rounded-lg" />
        <Skeleton className="h-16 w-full rounded-lg" />
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
        <EmptyDescription>
          Пользователь сейчас не авторизован ни на одном устройстве.
        </EmptyDescription>
      </Empty>
    )
  }

  return (
    <div className="space-y-2.5">
      {data.map((s) => {
        const dev = parseDeviceInfo(s.user_agent)
        return (
          <div
            key={s.session_id}
            className="flex items-center justify-between gap-3 rounded-lg border bg-card p-3.5 text-sm transition-colors"
          >
            <div className="flex min-w-0 items-start gap-3">
              <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                {dev.icon === "tv" ? (
                  <Tv className="size-4" />
                ) : dev.icon === "phone" ? (
                  <Smartphone className="size-4" />
                ) : (
                  <Laptop className="size-4" />
                )}
              </div>
              <div className="min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-foreground">{dev.title}</span>
                  {s.is_current && (
                    <Badge variant="outline" className="border-primary/40 text-primary font-normal text-[11px]">
                      текущая сессия
                    </Badge>
                  )}
                </div>
                <p className="truncate text-xs text-muted-foreground font-mono">
                  {s.ip ?? "IP неизвестен"} · вход {fmt(s.created_at)}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  последняя активность: {fmt(s.last_seen_at)}
                </p>
              </div>
            </div>

            {/* Активную сессию нельзя завершить из списка */}
            {!s.is_current && (
              <Button
                size="sm"
                variant="outline"
                className="shrink-0 text-xs"
                disabled={revoke.isPending}
                onClick={() => revoke.mutate(s.session_id)}
              >
                Завершить
              </Button>
            )}
          </div>
        )
      })}
    </div>
  )
}
