import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { AlertCircle } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { Button } from "@/components/shadsnui/button"
import { ButtonGroup } from "@/components/shadsnui/button-group"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/shadsnui/card"
import { Progress, ProgressTrack, ProgressIndicator } from "@/components/shadsnui/progress"
import { Skeleton } from "@/components/shadsnui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"
import { StatCard } from "@/components/charts/StatCard"

interface Page<T> {
  items: T[]
  total: number
}

interface PaymentsSummary {
  revenue: string
  paid_count: number
  failed_count: number
  refunded_count: number
  pending_count: number
}

interface ProviderRevenue {
  provider: string
  revenue: string
  count: number
}

interface ServiceSales {
  service_id: number
  name: string
  sold: number
  remaining_keys: number | null
}

interface PromoSummary {
  total_redemptions: number
}

interface PromoCodeStat {
  id: number
  code: string
  used_count: number
  max_uses: number | null
  remaining: number | null
}

interface AdvancedSummary {
  avg_days_to_first_payment: number | null
  churn: { inactive_days: number; churn_rate: number; total_accounts: number; churned_accounts: number }
  roi: { available: boolean; reason: string }
}

const PERIODS = [
  { value: "7", label: "7 дней" },
  { value: "30", label: "30 дней" },
  { value: "90", label: "90 дней" },
] as const

function sinceFor(days: string): string {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() - Number(days))
  return d.toISOString()
}

function fmtAmount(v: string | undefined): string {
  if (v === undefined) return "—"
  const n = Number(v)
  return Number.isFinite(n) ? n.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) : v
}

/** Список долей провайдеров в выручке — прогресс-бары вместо полноценного
 * графика: значений мало (число подключённых провайдеров), сравнение долей
 * читается лучше в виде шкал, чем точками на оси времени. */
function ProviderRevenueCard({ items, isLoading }: { items: ProviderRevenue[] | undefined; isLoading: boolean }) {
  const max = Math.max(1, ...(items ?? []).map((i) => Number(i.revenue)))
  return (
    <Card>
      <CardHeader>
        <CardTitle>Доход по провайдерам</CardTitle>
        <CardDescription>Оплаченные платежи за период</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && (
          <>
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </>
        )}
        {!isLoading && (items?.length ?? 0) === 0 && (
          <p className="text-sm text-muted-foreground">Оплаченных платежей за период нет.</p>
        )}
        {items?.map((p) => (
          <Progress key={p.provider} value={(Number(p.revenue) / max) * 100}>
            <div className="flex w-full items-center justify-between text-sm">
              <span className="font-medium">{p.provider}</span>
              <span className="text-muted-foreground">
                {fmtAmount(p.revenue)} · {p.count} {p.count === 1 ? "платёж" : "платежей"}
              </span>
            </div>
            <ProgressTrack>
              <ProgressIndicator />
            </ProgressTrack>
          </Progress>
        ))}
      </CardContent>
    </Card>
  )
}

function TopServicesCard({ items, isLoading }: { items: ServiceSales[] | undefined; isLoading: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Топ услуг</CardTitle>
        <CardDescription>По числу выданных за всё время</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className="h-32 w-full" />}
        {!isLoading && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Услуга</TableHead>
                <TableHead className="text-right">Продано</TableHead>
                <TableHead className="text-right">Остаток ключей</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(items ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={3} className="py-6 text-center text-sm text-muted-foreground">
                    Продаж пока нет
                  </TableCell>
                </TableRow>
              )}
              {items?.map((s) => (
                <TableRow key={s.service_id}>
                  <TableCell className="font-medium">{s.name}</TableCell>
                  <TableCell className="text-right tabular-nums">{s.sold}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {s.remaining_keys ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

function TopPromoCard({ items, isLoading }: { items: PromoCodeStat[] | undefined; isLoading: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Топ промокодов</CardTitle>
        <CardDescription>По числу использований за всё время</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className="h-32 w-full" />}
        {!isLoading && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Код</TableHead>
                <TableHead className="text-right">Использован</TableHead>
                <TableHead className="text-right">Остаток</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(items ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={3} className="py-6 text-center text-sm text-muted-foreground">
                    Промокодов пока нет
                  </TableCell>
                </TableRow>
              )}
              {items?.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-mono font-medium">{p.code}</TableCell>
                  <TableCell className="text-right tabular-nums">{p.used_count}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {p.remaining ?? "∞"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

function AdvancedCard({ data, isLoading }: { data: AdvancedSummary | undefined; isLoading: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Продвинутая аналитика</CardTitle>
        <CardDescription>Только для владельца — доступ отдельным правом</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className="h-16 w-full" />}
        {!isLoading && data && (
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <p className="text-xs text-muted-foreground">До первой оплаты</p>
              <p className="text-lg font-semibold tabular-nums">
                {data.avg_days_to_first_payment !== null
                  ? `${data.avg_days_to_first_payment.toFixed(1)} дн.`
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">
                Churn (неактивны {data.churn.inactive_days} дн.)
              </p>
              <p className="text-lg font-semibold tabular-nums">
                {(data.churn.churn_rate * 100).toFixed(1)}%
              </p>
              <p className="text-xs text-muted-foreground">
                {data.churn.churned_accounts} из {data.churn.total_accounts}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">ROI</p>
              <p className="text-sm text-muted-foreground">
                {data.roi.available ? "доступен" : data.roi.reason}
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function DashboardPage() {
  const { me, can } = useAuth()
  const [period, setPeriod] = useState<(typeof PERIODS)[number]["value"]>("30")
  const since = useMemo(() => sinceFor(period), [period])

  const canBasic = can("analytics.basic.read")
  const canAdvanced = can("analytics.advanced.read")

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["dash-payments-summary", since],
    queryFn: async () =>
      (await api.get<PaymentsSummary>("/v1/admin/analytics/basic/payments", { params: { since } })).data,
    enabled: canBasic,
  })

  const { data: byProvider, isLoading: byProviderLoading } = useQuery({
    queryKey: ["dash-payments-by-provider", since],
    queryFn: async () =>
      (
        await api.get<Page<ProviderRevenue>>("/v1/admin/analytics/basic/payments/by-provider", {
          params: { since, limit: 6 },
        })
      ).data.items,
    enabled: canBasic,
  })

  const { data: topServices, isLoading: topServicesLoading } = useQuery({
    queryKey: ["dash-top-services"],
    queryFn: async () =>
      (await api.get<Page<ServiceSales>>("/v1/admin/analytics/basic/services/top", { params: { limit: 5 } }))
        .data.items,
    enabled: canBasic,
  })

  const { data: promoSummary } = useQuery({
    queryKey: ["dash-promo-summary"],
    queryFn: async () => (await api.get<PromoSummary>("/v1/admin/analytics/basic/promo")).data,
    enabled: canBasic,
  })

  const { data: topPromo, isLoading: topPromoLoading } = useQuery({
    queryKey: ["dash-top-promo"],
    queryFn: async () =>
      (await api.get<Page<PromoCodeStat>>("/v1/admin/analytics/basic/promo/top", { params: { limit: 5 } }))
        .data.items,
    enabled: canBasic,
  })

  const { data: advanced, isLoading: advancedLoading } = useQuery({
    queryKey: ["dash-advanced-summary"],
    queryFn: async () => (await api.get<AdvancedSummary>("/v1/admin/analytics/advanced/summary")).data,
    enabled: canAdvanced,
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Добро пожаловать, {me?.login}</h1>
          <p className="text-sm text-muted-foreground">Сводка за выбранный период.</p>
        </div>
        {canBasic && (
          <ButtonGroup>
            {PERIODS.map((p) => (
              <Button
                key={p.value}
                type="button"
                size="sm"
                variant="outline"
                aria-pressed={p.value === period}
                onClick={() => setPeriod(p.value)}
                className={p.value === period ? "bg-accent text-accent-foreground" : undefined}
              >
                {p.label}
              </Button>
            ))}
          </ButtonGroup>
        )}
      </div>

      {!canBasic ? (
        <Card>
          <CardContent className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <AlertCircle className="size-4 shrink-0" />
            Недостаточно прав для просмотра аналитики.
          </CardContent>
        </Card>
      ) : (
        <div className="animate-in fade-in duration-300" key={period}>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Доход за период" value={summaryLoading ? undefined : fmtAmount(summary?.revenue)} />
            <StatCard label="Оплачено заказов" value={summaryLoading ? undefined : summary?.paid_count} />
            <StatCard label="Ожидают оплаты" value={summaryLoading ? undefined : summary?.pending_count} />
            <StatCard label="Погашено промокодов" value={promoSummary?.total_redemptions} />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <ProviderRevenueCard items={byProvider} isLoading={byProviderLoading} />
            <TopServicesCard items={topServices} isLoading={topServicesLoading} />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <TopPromoCard items={topPromo} isLoading={topPromoLoading} />
            {canAdvanced && <AdvancedCard data={advanced} isLoading={advancedLoading} />}
          </div>
        </div>
      )}
    </div>
  )
}
