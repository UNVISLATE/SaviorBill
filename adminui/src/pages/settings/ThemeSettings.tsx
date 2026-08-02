import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Loader2, RotateCcw } from "lucide-react"

import { api } from "@/api/api.ts"
import { useSettingsMap } from "@/hooks/use-settings-map"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/shadsnui/card"
import { ColorPicker, parseColor } from "@/components/shadsnui/fill-picker/color-picker"
import { Label } from "@/components/shadsnui/label"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/shadsnui/popover"
import { Skeleton } from "@/components/shadsnui/skeleton"

/** Роли цветов темы — ключи внутри JSON-настройки `ui.{scope}.theme`. */
const THEME_COLORS = [
  { key: "primary", label: "Акцент", fallback: "#009080" },
  { key: "primaryDark", label: "Акцент тёмный", fallback: "#0C5E53" },
  { key: "surface", label: "Подложка", fallback: "#0D504B" },
] as const

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (next: string) => void
}) {
  const parsed = parseColor(value) ?? parseColor("#009080")!

  return (
    <div className="flex items-center justify-between gap-4">
      <Label className="font-normal">{label}</Label>
      <Popover>
        <PopoverTrigger
          render={
            <button
              type="button"
              className="flex items-center gap-2 rounded-md border px-2 py-1.5 text-xs transition-colors hover:bg-accent"
            >
              <span
                className="size-5 rounded border"
                style={{ backgroundColor: value }}
              />
              <span className="font-mono uppercase">{value}</span>
            </button>
          }
        />
        <PopoverContent align="end" className="w-auto border-0 bg-transparent p-0 shadow-none">
          <ColorPicker.Root
            value={parsed}
            onValueChange={(_next, _formatted, formats) => onChange(formats.hex)}
          >
            <ColorPicker.Area />
            <ColorPicker.Hue />
            <ColorPicker.ChannelInput />
          </ColorPicker.Root>
        </PopoverContent>
      </Popover>
    </div>
  )
}

/**
 * Цвета темы (`ui.{scope}.theme`) — раньше эту JSON-настройку можно было
 * задать только руками через Raw settings, не видя результата.
 */
export function ThemeSettings({ scope }: { scope: "admin" | "client" }) {
  const qc = useQueryClient()
  const { map, isLoading } = useSettingsMap()
  const savedRaw = map.get(`ui.${scope}.theme`) ?? ""

  const saved = (() => {
    try {
      const parsed = JSON.parse(savedRaw || "{}")
      return typeof parsed === "object" && parsed ? (parsed as Record<string, string>) : {}
    } catch {
      return {}
    }
  })()

  const [draft, setDraft] = useState<Record<string, string> | null>(null)
  const current = draft ?? saved
  const dirty = JSON.stringify(current) !== JSON.stringify(saved)

  const save = useMutation({
    mutationFn: async (value: string) =>
      api.post(`/v1/admin/settings/ui/${scope}.theme`, { value }),
    onSuccess: () => {
      toastSuccess("Тема сохранена")
      setDraft(null)
      void qc.invalidateQueries({ queryKey: ["admin-settings-all"] })
      void qc.invalidateQueries({ queryKey: ["branding-admin"] })
    },
    onError: () => toastError("Не удалось сохранить тему"),
  })

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Цвета темы</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Цвета темы</CardTitle>
        <CardDescription>
          Отдаются клиенту вместе с остальным брендингом.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {THEME_COLORS.map((c) => (
          <ColorField
            key={c.key}
            label={c.label}
            value={current[c.key] ?? c.fallback}
            onChange={(next) => setDraft({ ...current, [c.key]: next })}
          />
        ))}
      </CardContent>
      <CardFooter className="justify-between gap-2">
        <Button
          size="sm"
          variant="ghost"
          disabled={save.isPending || Object.keys(current).length === 0}
          onClick={() => {
            setDraft({})
            save.mutate("")
          }}
        >
          <RotateCcw className="size-4" /> Сбросить
        </Button>
        {dirty && (
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
              Отменить
            </Button>
            <Button
              size="sm"
              disabled={save.isPending}
              onClick={() => save.mutate(JSON.stringify(current))}
            >
              {save.isPending && <Loader2 className="size-4 animate-spin" />}
              Сохранить
            </Button>
          </div>
        )}
      </CardFooter>
    </Card>
  )
}
