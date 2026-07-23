import { useQuery } from "@tanstack/react-query"
import { ShieldOff, Ticket } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { Skeleton } from "@/components/shadsnui/skeleton"
import { Empty, EmptyDescription, EmptyMedia, EmptyTitle } from "@/components/shadsnui/empty"

interface PromoUse {
  id: number
  promocode_id: number
  code: string
  order_id: number | null
  created_at: string
}

interface Page<T> {
  items: T[]
  total: number
}

/** Активированные пользователем промокоды — видно только в чужом (админском)
 * просмотре профиля, требует `users.read`. */
export function ProfilePromocodesSection({ userId }: { userId?: number }) {
  const { can } = useAuth()
  const allowed = can("users.read")

  const { data, isLoading } = useQuery({
    queryKey: ["admin-user-promocodes", userId],
    queryFn: async () =>
      (
        await api.get<Page<PromoUse>>(`/v1/admin/users/${userId}/promocodes`, {
          params: { limit: 50 },
        })
      ).data,
    enabled: allowed && !!userId,
  })

  if (!allowed) {
    return (
      <Empty>
        <EmptyMedia>
          <ShieldOff className="size-8 text-muted-foreground" />
        </EmptyMedia>
        <EmptyTitle>Недостаточно прав</EmptyTitle>
        <EmptyDescription>Нужно право users.read.</EmptyDescription>
      </Empty>
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (!data || data.items.length === 0) {
    return (
      <Empty>
        <EmptyMedia>
          <Ticket className="size-8 text-muted-foreground" />
        </EmptyMedia>
        <EmptyTitle>Промокоды не активировались</EmptyTitle>
        <EmptyDescription>Здесь появится история активаций.</EmptyDescription>
      </Empty>
    )
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">Всего активаций: {data.total}</p>
      {data.items.map((p) => (
        <div
          key={p.id}
          className="flex items-center justify-between rounded-lg border p-3 text-sm"
        >
          <div>
            <p className="font-mono font-medium">{p.code}</p>
            {p.order_id && (
              <p className="text-xs text-muted-foreground">Заказ #{p.order_id}</p>
            )}
          </div>
          <span className="text-xs text-muted-foreground">
            {new Date(p.created_at).toLocaleString("ru-RU")}
          </span>
        </div>
      ))}
    </div>
  )
}
