import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { Badge } from "@/components/shadsnui/badge"
import { Skeleton } from "@/components/shadsnui/skeleton"
import { Empty, EmptyDescription, EmptyMedia, EmptyTitle } from "@/components/shadsnui/empty"
import { PackageOpen } from "lucide-react"

interface Order {
  id: number
  service_id: number
  payment_id: number | null
  status: string
  price: string
}

interface Page<T> {
  items: T[]
  total: number
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  active: "default",
  pending: "secondary",
  expired: "outline",
  cancelled: "destructive",
  error: "destructive",
}

export function ProfileServicesSection() {
  const { data, isLoading } = useQuery({
    queryKey: ["user-services"],
    queryFn: async () => (await api.get<Page<Order>>("/v1/user/services", { params: { limit: 50 } })).data,
  })

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    )
  }

  if (!data || data.items.length === 0) {
    return (
      <Empty>
        <EmptyMedia>
          <PackageOpen className="size-8 text-muted-foreground" />
        </EmptyMedia>
        <EmptyTitle>Пока нет товаров</EmptyTitle>
        <EmptyDescription>Выданные услуги появятся здесь после покупки.</EmptyDescription>
      </Empty>
    )
  }

  return (
    <div className="space-y-2">
      {data.items.map((o) => (
        <div
          key={o.id}
          className="flex items-center justify-between rounded-lg border p-3 text-sm"
        >
          <div>
            <p className="font-medium">Услуга #{o.service_id}</p>
            <p className="text-xs text-muted-foreground">Заказ #{o.id}</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="tabular-nums">{o.price} ₽</span>
            <Badge variant={STATUS_VARIANT[o.status] ?? "outline"}>{o.status}</Badge>
          </div>
        </div>
      ))}
    </div>
  )
}
