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

export type FieldKind = "text" | "number" | "select" | "switch" | "rates"

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
}

function HintIcon({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            aria-label={text}
            className="inline-flex text-muted-foreground/70 transition-colors hover:text-foreground"
          >
            <Info className="size-3.5" />
          </button>
        }
      />
      <TooltipContent>{text}</TooltipContent>
    </Tooltip>
  )
}

/** Редактор пар «валюта → курс» вместо ручного набора JSON руками. */
function RatesEditor({
  value,
  onChange,
}: {
  value: string
  onChange: (next: string) => void
}) {
  const pairs = useMemo(() => {
    try {
      const parsed = JSON.parse(value || "{}") as Record<string, unknown>
      return Object.entries(parsed).map(([code, rate]) => ({ code, rate: String(rate) }))
    } catch {
      return []
    }
  }, [value])

  const broken = value.trim() !== "" && (() => {
    try {
      JSON.parse(value)
      return false
    } catch {
      return true
    }
  })()

  function write(next: { code: string; rate: string }[]) {
    const obj: Record<string, string> = {}
    for (const p of next) if (p.code.trim()) obj[p.code.trim().toUpperCase()] = p.rate
    onChange(Object.keys(obj).length ? JSON.stringify(obj) : "")
  }

  if (broken) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-destructive">
          В настройке лежит не-JSON — почините через Raw settings, чтобы вернуть табличный вид.
        </p>
        <Input value={value} onChange={(e) => onChange(e.target.value)} className="font-mono text-xs" />
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {pairs.length > 0 && (
        <div className="grid grid-cols-[6rem_1fr_auto] items-center gap-2 text-xs text-muted-foreground">
          <span>Валюта</span>
          <span>Курс к базовой</span>
          <span />
        </div>
      )}
      {pairs.map((p, i) => (
        <div key={i} className="grid grid-cols-[6rem_1fr_auto] items-center gap-2">
          <Input
            value={p.code}
            onChange={(e) => {
              const next = [...pairs]
              next[i] = { ...p, code: e.target.value.toUpperCase() }
              write(next)
            }}
            placeholder="USD"
            className="font-mono uppercase"
          />
          <Input
            value={p.rate}
            onChange={(e) => {
              const next = [...pairs]
              next[i] = { ...p, rate: e.target.value }
              write(next)
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
            onClick={() => write(pairs.filter((_, idx) => idx !== i))}
          >
            <X className="size-4" />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => write([...pairs, { code: "", rate: "" }])}
      >
        <Plus className="size-4" /> Добавить валюту
      </Button>
      {pairs.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Курсов нет — при оплате в другой валюте зачисление будет отклонено.
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
        className={cn(spec.suffix && "pr-12")}
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
 * Секция настроек — одна карточка со своим набором полей и СОБСТВЕННОЙ
 * кнопкой сохранения, которая появляется только когда в этой секции
 * что-то изменено (и сохраняет всю секцию разом, а не по полю).
 *
 * Раскладка: подпись слева, контрол справа фиксированной ширины — на широком
 * мониторе поля не растягиваются во весь экран. Длинные пояснения убраны
 * под иконку «i», чтобы строки оставались компактными.
 */
export function SettingsSection({
  title,
  description,
  fields,
  footerNote,
}: {
  title: string
  description?: string
  fields: SettingFieldSpec[]
  footerNote?: ReactNode
}) {
  const qc = useQueryClient()
  const { map, isLoading } = useSettingsMap()

  const saved = useMemo(() => {
    const o: Record<string, string> = {}
    for (const f of fields) o[f.key] = map.get(f.key) ?? ""
    return o
  }, [map, fields])

  const [draft, setDraft] = useState<Record<string, string> | null>(null)
  const current = draft ?? saved
  const changedKeys = fields.map((f) => f.key).filter((k) => current[k] !== saved[k])
  const dirty = changedKeys.length > 0

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
      setDraft(null)
      await qc.invalidateQueries({ queryKey: ["admin-settings-all"] })
    },
    onError: () => toastError(`Не удалось сохранить «${title}»`),
  })

  if (isLoading) {
    return (
      <Card>
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
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="divide-y">
        {fields.map((f) => {
          const control = (
            <FieldControl
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
      {(dirty || footerNote) && (
        <CardFooter className="justify-between gap-3">
          <span className="text-xs text-muted-foreground">
            {dirty ? `Не сохранено: ${changedKeys.length}` : footerNote}
          </span>
          {dirty && (
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => setDraft(null)} disabled={save.isPending}>
                Отменить
              </Button>
              <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
                {save.isPending && <Loader2 className="size-4 animate-spin" />}
                Сохранить
              </Button>
            </div>
          )}
        </CardFooter>
      )}
    </Card>
  )
}
