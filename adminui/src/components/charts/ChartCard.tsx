import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { cn } from "@/lib/utils"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/shadsnui/card"
import { ToggleGroup, ToggleGroupItem } from "@/components/shadsnui/toggle-group"

export interface ChartCardSeries {
  key: string
  label: string
  color: string
  /** Для двух Y-осей на разных шкалах (напр. CPU% и МБ). */
  yAxisId?: string
}

export interface ChartCardPeriod {
  value: string
  label: string
}

interface ChartCardProps {
  title: string
  description?: string
  data: readonly object[]
  xKey: string
  series: ChartCardSeries[]
  xTickFormatter?: (v: string) => string
  tooltipLabelFormatter?: (v: string) => string
  periods?: readonly ChartCardPeriod[]
  period?: string
  onPeriodChange?: (v: string) => void
  totalLabel?: string
  totalValue?: string | number
  height?: number
  className?: string
}

interface TooltipItem {
  dataKey?: string | number
  name?: string
  value?: string | number
  color?: string
}

/** Кастомный тултип, оформленный в стиле карточек проекта — иначе дефолтный
 * белый тултип recharts выглядит "криво" на тёмной теме. */
function ChartTooltip({
  active,
  payload,
  label,
  labelFormatter,
}: {
  active?: boolean
  payload?: TooltipItem[]
  label?: string
  labelFormatter?: (v: string) => string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <div className="mb-1 font-medium text-muted-foreground">
        {labelFormatter && typeof label === "string" ? labelFormatter(label) : label}
      </div>
      {payload.map((p) => (
        <div key={p.dataKey as string} className="flex items-center gap-2">
          <span className="size-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-muted-foreground">{p.name}:</span>
          <span className="font-semibold">{p.value}</span>
        </div>
      ))}
    </div>
  )
}

/** Сам график + подпись суммы, без внешней Card — переиспользуется и когда
 * график встраивается в уже существующую Card (SystemOverview). */
export function ChartCardBody({
  data,
  xKey,
  series,
  xTickFormatter,
  tooltipLabelFormatter,
  totalLabel,
  totalValue,
  height = 220,
}: Pick<
  ChartCardProps,
  "data" | "xKey" | "series" | "xTickFormatter" | "tooltipLabelFormatter" | "totalLabel" | "totalValue" | "height"
>) {
  const secondYAxisId = series.find((s) => s.yAxisId && s.yAxisId !== series[0]?.yAxisId)?.yAxisId

  return (
    <>
      <div style={{ height }} className="w-full px-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <defs>
              {series.map((s) => (
                <linearGradient key={s.key} id={`chart-fill-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={s.color} stopOpacity={0.35} />
                  <stop offset="95%" stopColor={s.color} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" opacity={0.15} vertical={false} />
            <XAxis
              dataKey={xKey}
              tick={{ fontSize: 11 }}
              tickFormatter={xTickFormatter}
              tickLine={false}
              axisLine={false}
              minTickGap={24}
            />
            <YAxis
              yAxisId={series[0]?.yAxisId ?? "left"}
              allowDecimals={false}
              tick={{ fontSize: 11 }}
              width={32}
              tickLine={false}
              axisLine={false}
            />
            {secondYAxisId && (
              <YAxis
                yAxisId={secondYAxisId}
                orientation="right"
                tick={{ fontSize: 11 }}
                width={40}
                tickLine={false}
                axisLine={false}
              />
            )}
            <Tooltip
              content={<ChartTooltip labelFormatter={tooltipLabelFormatter} />}
              cursor={{ stroke: "var(--foreground)", strokeOpacity: 0.15 }}
              wrapperStyle={{ outline: "none" }}
              isAnimationActive={false}
            />
            {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
            {series.map((s) => (
              <Area
                key={s.key}
                yAxisId={s.yAxisId ?? "left"}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                fill={`url(#chart-fill-${s.key})`}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {totalLabel && (
        <div className="mt-1 text-center text-sm text-muted-foreground">
          {totalLabel}: <span className="font-semibold text-foreground">{totalValue ?? "—"}</span>
        </div>
      )}
    </>
  )
}

/**
 * Общая карточка графика: full-bleed область графика, группа кнопок периода
 * (overlay сверху справа) и подпись суммы под ней. Используется на страницах
 * Пользователей и Системы — единая точка правки внешнего вида всех графиков.
 */
export function ChartCard({
  title,
  description,
  periods,
  period,
  onPeriodChange,
  className,
  ...body
}: ChartCardProps) {
  return (
    <Card className={cn("relative overflow-hidden", className)}>
      <CardHeader className={cn(periods ? "flex-row items-start justify-between gap-3" : undefined)}>
        <div>
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        {periods && period && onPeriodChange && (
          <ToggleGroup value={[period]} onValueChange={(v) => v[0] && onPeriodChange(v[0])}>
            {periods.map((p) => (
              <ToggleGroupItem key={p.value} value={p.value} size="sm">
                {p.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        )}
      </CardHeader>

      <CardContent className="px-0">
        <ChartCardBody {...body} />
      </CardContent>
    </Card>
  )
}
