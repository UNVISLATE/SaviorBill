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
import { Button } from "@/components/shadsnui/button"
import { ButtonGroup } from "@/components/shadsnui/button-group"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/shadsnui/card"

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

      {/* Подпись суммы рисуем только когда карточка не показала её в шапке
          (SystemOverview встраивает ChartCardBody в свою Card). */}
      {totalLabel && totalValue !== undefined && (
        <div className="px-4 pb-3 text-center text-sm text-muted-foreground">
          {totalLabel}: <span className="font-semibold text-foreground">{totalValue}</span>
        </div>
      )}
    </>
  )
}

/**
 * Общая карточка графика: график занимает низ карточки целиком (full-bleed,
 * без внутренних отступов и подписи снизу), заголовок с метрикой и
 * переключателем периода — сверху. Диапазоны — один сегментированный
 * контрол, а не россыпь отдельных кнопок.
 */
export function ChartCard({
  title,
  description,
  periods,
  period,
  onPeriodChange,
  className,
  totalLabel,
  totalValue,
  ...body
}: ChartCardProps) {
  return (
    <Card className={cn("relative gap-0 overflow-hidden pb-0", className)}>
      <CardHeader className="flex-row items-start justify-between gap-3 pb-3">
        <div className="space-y-1">
          <CardTitle>{title}</CardTitle>
          {totalValue !== undefined ? (
            <div className="flex items-baseline gap-2">
              <span className="text-sm text-muted-foreground">
                <span className="font-semibold text-foreground tabular-nums">{totalValue}</span>
                {totalLabel ? ` ${totalLabel}` : ""}
              </span>
            </div>
          ) : (
            description && <CardDescription>{description}</CardDescription>
          )}
        </div>
        {periods && period && onPeriodChange && (
          <ButtonGroup>
            {periods.map((p) => (
              <Button
                key={p.value}
                type="button"
                size="sm"
                variant="outline"
                aria-pressed={p.value === period}
                onClick={() => onPeriodChange(p.value)}
                className={cn(
                  "transition-colors",
                  p.value === period && "bg-accent text-accent-foreground",
                )}
              >
                {p.label}
              </Button>
            ))}
          </ButtonGroup>
        )}
      </CardHeader>

      <CardContent
        // Смена периода — новый key, чтобы график появлялся с анимацией
        // входа, а не подменял точки без обратной связи.
        key={period}
        className="animate-in fade-in slide-in-from-bottom-1 px-0 duration-300"
      >
        <ChartCardBody {...body} />
      </CardContent>
    </Card>
  )
}
