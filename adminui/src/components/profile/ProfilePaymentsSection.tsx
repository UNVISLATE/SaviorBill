import { useQuery } from "@tanstack/react-query"
import { CreditCard } from "lucide-react"

import { api } from "@/lib/api"
import { Badge } from "@/components/shadsnui/badge"
import { Skeleton } from "@/components/shadsnui/skeleton"
import { Empty, EmptyDescription, EmptyMedia, EmptyTitle } from "@/components/shadsnui/empty"

interface Payment {
  id: number
  provider: string
  amount: string
  currency: string
  status: string
  target: string
  created_at: string
}

interface Page<T> {
  items: T[]
  total: number
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  succeeded: "default",
  paid: "default",
  pending: "secondary",
  failed: "destructive",
  cancelled: "outline",
}

export function ProfilePaymentsSection() {
  const { data, isLoading } = useQuery({
    queryKey: ["user-purchases"],
    queryFn: async () =>
      (await api.get<Page<Payment>>("/v1/user/purchases", { params: { limit: 50 } })).data,
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
          <CreditCard className="size-8 text-muted-foreground" />
        </EmptyMedia>
        <EmptyTitle>Пока нет платежей</EmptyTitle>
        <EmptyDescription>История платежей появится здесь.</EmptyDescription>
      </Empty>
    )
  }

  return (
    <div className="space-y-2">
      {data.items.map((p) => (
        <div
          key={p.id}
          className="flex items-center justify-between rounded-lg border p-3 text-sm"
        >
          <div>
            <p className="font-medium">
              {p.target === "service" ? "Оплата услуги" : "Пополнение баланса"}
            </p>
            <p className="text-xs text-muted-foreground">
              {p.provider} · {new Date(p.created_at).toLocaleDateString("ru-RU")}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="tabular-nums">
              {p.amount} {p.currency}
            </span>
            <Badge variant={STATUS_VARIANT[p.status] ?? "outline"}>{p.status}</Badge>
          </div>
        </div>
      ))}
    </div>
  )
}
