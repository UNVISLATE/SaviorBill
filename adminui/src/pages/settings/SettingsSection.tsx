import { useMemo, useState, type ReactNode } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Info, Loader2, Plus, X } from "lucide-react"

import { api } from "@/api/api.ts"
import { cn } from "@/lib/utils"
import { toastError, toastSuccess } from "@/lib/toast"
import { useSettingsMap } from "@/hooks/use-settings-map"
import { Button } from "@/components/shadsnui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/shadsnui/card"
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/shadsnui/combobox"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import { Switch } from "@/components/shadsnui/switch"
import { Skeleton } from "@/components/shadsnui/skeleton"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/shadsnui/tooltip"

export type FieldKind =
  | "text"
  | "number"
  | "select"
  | "switch"
  | "rates"
  | "currency"

export interface SettingFieldSpec {
  key: string
  label: string
  /** Короткая подсказка — прячется под иконку «i», не занимает место в строке. */
  hint?: string
  kind?: FieldKind
  placeholder?: string
  /** Для `kind: "select"`. */
  options?: { value: string; label: string }[]
  /** Единица измерения справа от поля (сек, %, байт…). */
  suffix?: string
  /** Поле на всю ширину карточки, с подписью сверху (для таблиц/JSON). */
  wide?: boolean
  /** Показывать поле только если другое поле секции имеет одно из значений. */
  showIf?: { key: string; equals: string[] }
}

/** Ходовые валюты для подсказки в combobox — ввести можно любой ISO-код. */
const CURRENCIES = [
  ["RUB", "Российский рубль"],
  ["USD", "Доллар США"],
  ["EUR", "Евро"],
  ["GBP", "Фунт стерлингов"],
  ["CNY", "Юань"],
  ["KZT", "Тенге"],
  ["BYN", "Белорусский рубль"],
  ["UAH", "Гривна"],
  ["TRY", "Турецкая лира"],
  ["AED", "Дирхам ОАЭ"],
  ["GEL", "Лари"],
  ["AMD", "Драм"],
  ["UZS", "Сум"],
  ["JPY", "Иена"],
  ["CHF", "Швейцарский франк"],
  ["PLN", "Злотый"],
  ["INR", "Рупия"],
  ["BRL", "Реал"],
] as const

function HintIcon({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            aria-label={text}
            className="inline-flex text-muted-foreground/60 transition-colors hover:text-foreground"
          >
            <Info className="size-3.5" />
          </button>
        }
      />
      <TooltipContent>{text}</TooltipContent>
    </Tooltip>
  )
}

function CurrencyPicker({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (next: string) => void
  placeholder?: string
}) {
  const items = useMemo(() => CURRENCIES.map(([code, name]) => `${code} — ${name}`), [])

  return (
    <Combobox
      items={items}
      value={value ? (items.find((i) => i.startsWith(`${value} `)) ?? value) : null}
      onValueChange={(v) => onChange(typeof v === "string" ? v.slice(0, 3).toUpperCase() : "")}
    >
      <ComboboxInput placeholder={placeholder ?? "Код валюты"} />
      <ComboboxContent>
        <ComboboxEmpty>Ничего не найдено — можно ввести код вручную.</ComboboxEmpty>
        <ComboboxList>
          {(item: string) => (
            <ComboboxItem key={item} value={item}>
              {item}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}

interface RateRow {
  code: string
  rate: string
}

function parseRates(raw: string): RateRow[] {
  try {
    const parsed = JSON.parse(raw || "{}") as Record<string, unknown>
    return Object.entries(parsed).map(([code, rate]) => ({ code, rate: String(rate) }))
  } catch {
    return []
  }
}

/** JSON только из заполненных строк — пустая заготовка живёт в локальном
 * состоянии редактора и наружу не уезжает. */
function serializeRates(rows: RateRow[]): string {
  const obj: Record<string, string> = {}
  for (const r of rows) {
    const code = r.code.trim().toUpperCase()
    if (code) obj[code] = r.rate.trim()
  }
  return Object.keys(obj).length ? JSON.stringify(obj) : ""
}

/**
 * Редактор пар «валюта → курс» вместо ручного JSON.
 *
 * Строки держим в СВОЁМ состоянии: раньше список выводился прямо из JSON, а
 * сериализация выбрасывала записи с пустым кодом — из-за чего только что
 * добавленная пустая строка исчезала в тот же кадр и кнопка «Добавить»
 * выглядела нерабочей.
 */
function RatesEditor({
  value,
  onChange,
}: {
  value: string
  onChange: (next: string) => void
}) {
  const [rows, setRows] = useState<RateRow[]>(() => parseRates(value))

  const broken =
    value.trim() !== "" &&
    (() => {
      try {
        JSON.parse(value)
        return false
      } catch {
        return true
      }
    })()

  function update(next: RateRow[]) {
    setRows(next)
    onChange(serializeRates(next))
  }

  if (broken) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-destructive">
          Значение не является JSON. Почините через Raw settings.
        </p>
        <Input value={value} onChange={(e) => onChange(e.target.value)} className="font-mono text-xs" />
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div key={i} className="grid grid-cols-[7rem_1fr_auto] items-center gap-2">
          <Input
            value={r.code}
            onChange={(e) => {
              const next = [...rows]
              next[i] = { ...r, code: e.target.value.toUpperCase() }
              update(next)
            }}
            placeholder="USD"
            className="font-mono uppercase"
          />
          <Input
            value={r.rate}
            onChange={(e) => {
              const next = [...rows]
              next[i] = { ...r, rate: e.target.value }
              update(next)
            }}
            placeholder="95.5"
            inputMode="decimal"
            className="font-mono"
          />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="size-8 text-muted-foreground hover:text-destructive"
            onClick={() => update(rows.filter((_, idx) => idx !== i))}
          >
            <X className="size-4" />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => update([...rows, { code: "", rate: "" }])}
      >
        <Plus className="size-4" /> Добавить валюту
      </Button>
      {rows.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Курсов нет — оплата в другой валюте будет отклонена.
        </p>
      )}
    </div>
  )
}

function FieldControl({
  spec,
  value,
  onChange,
}: {
  spec: SettingFieldSpec
  value: string
  onChange: (next: string) => void
}) {
  const kind = spec.kind ?? "text"

  if (kind === "switch") {
    return (
      <Switch
        checked={value.toLowerCase() === "true"}
        onCheckedChange={(checked) => onChange(String(checked))}
      />
    )
  }

  if (kind === "currency") {
    return <CurrencyPicker value={value} onChange={onChange} placeholder={spec.placeholder} />
  }

  if (kind === "select") {
    return (
      <Select value={value || undefined} onValueChange={(v) => v && onChange(v)}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder={spec.placeholder ?? "Не задано"} />
        </SelectTrigger>
        <SelectContent>
          {spec.options?.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  }

  if (kind === "rates") {
    return <RatesEditor value={value} onChange={onChange} />
  }

  return (
    <div className="relative">
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={spec.placeholder}
        inputMode={kind === "number" ? "numeric" : undefined}
        className={cn(spec.suffix && "pr-14")}
      />
      {spec.suffix && (
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-muted-foreground">
          {spec.suffix}
        </span>
      )}
    </div>
  )
}

/**
 * Секция настроек — карточка со своим набором полей и СОБСТВЕННОЙ кнопкой
 * сохранения, которая появляется только при изменениях в этой секции и
 * сохраняет её целиком.
 *
 * Раскладка: подпись слева, контрол справа фиксированной ширины — на широком
 * мониторе поля не растягиваются во весь экран. Длинные пояснения — под «i».
 */
export function SettingsSection({
  title,
  description,
  fields,
  footerNote,
  actions,
}: {
  title: string
  description?: string
  fields: SettingFieldSpec[]
  footerNote?: ReactNode
  /** Доп. кнопки в футере. Функция получает ТЕКУЩИЕ (черновые) значения
   * секции — чтобы, например, кнопка проверки источника работала с тем, что
   * выбрано сейчас, а не с последним сохранённым. */
  actions?: ReactNode | ((current: Record<string, string>) => ReactNode)
}) {
  const qc = useQueryClient()
  const { map, isLoading } = useSettingsMap()

  const saved = useMemo(() => {
    const o: Record<string, string> = {}
    for (const f of fields) o[f.key] = map.get(f.key) ?? ""
    return o
  }, [map, fields])

  const [draft, setDraft] = useState<Record<string, string> | null>(null)
  // Меняется при отмене/сохранении — по нему пересоздаются поля с внутренним
  // состоянием (редактор курсов), чтобы они подхватили новое значение.
  const [resetToken, setResetToken] = useState(0)

  const current = draft ?? saved
  const changedKeys = fields.map((f) => f.key).filter((k) => current[k] !== saved[k])
  const dirty = changedKeys.length > 0

  const visible = fields.filter(
    (f) => !f.showIf || f.showIf.equals.includes(current[f.showIf.key] ?? ""),
  )

  function reset() {
    setDraft(null)
    setResetToken((t) => t + 1)
  }

  const save = useMutation({
    mutationFn: async () => {
      for (const key of changedKeys) {
        await api.put(`/v1/admin/settings/raw/${encodeURIComponent(key)}`, {
          value: current[key],
        })
      }
    },
    onSuccess: async () => {
      toastSuccess(`«${title}» сохранено`)
      reset()
      await qc.invalidateQueries({ queryKey: ["admin-settings-all"] })
    },
    onError: () => toastError(`Не удалось сохранить «${title}»`),
  })

  if (isLoading) {
    return (
      <Card className="mb-4 break-inside-avoid">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="mb-4 break-inside-avoid">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="divide-y">
        {visible.map((f) => {
          const control = (
            <FieldControl
              key={`${f.key}:${resetToken}`}
              spec={f}
              value={current[f.key] ?? ""}
              onChange={(next) => setDraft({ ...current, [f.key]: next })}
            />
          )
          const label = (
            <Label className="flex items-center gap-1.5 font-normal">
              {f.label}
              {f.hint && <HintIcon text={f.hint} />}
            </Label>
          )

          if (f.wide) {
            return (
              <div key={f.key} className="space-y-2 py-3 first:pt-0 last:pb-0">
                {label}
                {control}
              </div>
            )
          }
          return (
            <div
              key={f.key}
              className="flex items-center justify-between gap-6 py-3 first:pt-0 last:pb-0"
            >
              <div className="min-w-0">{label}</div>
              <div className="w-full max-w-56 shrink-0">{control}</div>
            </div>
          )
        })}
      </CardContent>
      {(dirty || footerNote || actions) && (
        <CardFooter className="flex-col items-stretch gap-3">
          {actions && (
            <div>{typeof actions === "function" ? actions(current) : actions}</div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              {dirty ? `Изменено полей: ${changedKeys.length}` : footerNote}
            </span>
            {dirty && (
              <div className="flex items-center gap-2">
                <Button size="sm" variant="ghost" onClick={reset} disabled={save.isPending}>
                  Отменить
                </Button>
                <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
                  {save.isPending && <Loader2 className="size-4 animate-spin" />}
                  Сохранить
                </Button>
              </div>
            )}
          </div>
        </CardFooter>
      )}
    </Card>
  )
}
