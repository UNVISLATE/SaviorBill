import { Badge } from "@/components/shadsnui/badge"
import { Card, CardContent, CardDescription, CardHeader } from "@/components/shadsnui/card"

/** Компактная карточка-метрика: значение крупно + необязательная динамика
 * бейджем. Общая для дашборда и страницы пользователей. */
export function StatCard({
  label,
  value,
  delta,
  deltaLabel,
}: {
  label: string
  value: number | string | undefined
  delta?: number
  deltaLabel?: string
}) {
  return (
    <Card size="sm" className="justify-between">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
      </CardHeader>
      <CardContent className="flex items-baseline gap-2">
        <span className="text-2xl font-semibold tabular-nums">{value ?? "—"}</span>
        {delta !== undefined && delta > 0 && (
          <Badge variant="outline" className="text-emerald-500">
            +{delta}
            {deltaLabel && <span className="ml-1 font-normal text-muted-foreground">{deltaLabel}</span>}
          </Badge>
        )}
      </CardContent>
    </Card>
  )
}
