import { useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { ImageOff, Loader2, Trash2, Upload } from "lucide-react"

import { api } from "@/api/api.ts"
import { uploadOwnMedia } from "@/api/media-upload.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { cn } from "@/lib/utils"
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
import { Skeleton } from "@/components/shadsnui/skeleton"

type Scope = "admin" | "client"
type Asset = "logo" | "favicon"

function mediaUrl(token: string | undefined | null): string | null {
  return token ? `/api/media/${token}` : null
}

/** Загрузка изображения и запись его токена в `ui.{scope}.{asset}`. */
function AssetSlot({
  scope,
  asset,
  label,
  note,
  token,
  onDone,
}: {
  scope: Scope
  asset: Asset
  label: string
  note: string
  token: string
  onDone: () => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<string | null>(null)

  const write = useMutation({
    mutationFn: async (value: string) =>
      api.post(`/v1/admin/settings/ui/${scope}.${asset}`, { value }),
    onSuccess: () => {
      toastSuccess(`${label} обновлён`)
      setPreview(null)
      onDone()
    },
    onError: () => toastError(`Не удалось сохранить ${label.toLowerCase()}`),
  })

  const upload = useMutation({
    mutationFn: async (file: File) => {
      // tag — метка для админки; сервер требует до 16 символов, только
      // латиница и цифры (никаких дефисов, см. mediaworker _TAG_RE).
      const { token: uploaded } = await uploadOwnMedia(file, { tag: `${scope}${asset}` })
      await api.post(`/v1/admin/settings/ui/${scope}.${asset}`, { value: uploaded })
    },
    onSuccess: () => {
      toastSuccess(`${label} обновлён`)
      setPreview(null)
      onDone()
    },
    onError: (err: unknown) => {
      setPreview(null)
      toastError(
        `Не удалось загрузить ${label.toLowerCase()}`,
        err instanceof Error ? err.message : undefined,
      )
    },
  })

  const busy = upload.isPending || write.isPending
  const shown = preview ?? mediaUrl(token)

  return (
    <div className="flex items-center gap-4">
      <div
        className={cn(
          "flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-lg border bg-muted/30",
          busy && "opacity-50",
        )}
      >
        {shown ? (
          <img src={shown} alt="" className="size-full object-contain" />
        ) : (
          <ImageOff className="size-5 text-muted-foreground/60" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{note}</p>
      </div>

      <div className="flex shrink-0 gap-1">
        <Button size="sm" variant="outline" disabled={busy} onClick={() => inputRef.current?.click()}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
          {token ? "Заменить" : "Загрузить"}
        </Button>
        {token && (
          <Button
            size="icon"
            variant="ghost"
            className="size-8 text-muted-foreground hover:text-destructive"
            disabled={busy}
            onClick={() => write.mutate("")}
            title="Сбросить к значению по умолчанию"
          >
            <Trash2 className="size-4" />
          </Button>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) {
            setPreview(URL.createObjectURL(file))
            upload.mutate(file)
          }
          e.target.value = ""
        }}
      />
    </div>
  )
}

function ScopeCard({
  scope,
  title,
  description,
}: {
  scope: Scope
  title: string
  description: string
}) {
  const qc = useQueryClient()
  const { map, isLoading } = useSettingsMap()
  const savedName = map.get(`ui.${scope}.name`) ?? ""
  const [name, setName] = useState<string | null>(null)
  const currentName = name ?? savedName
  const dirty = currentName !== savedName

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin-settings-all"] })
    void qc.invalidateQueries({ queryKey: ["branding-admin"] })
  }

  const saveName = useMutation({
    mutationFn: async () => api.post(`/v1/admin/settings/ui/${scope}.name`, { value: currentName }),
    onSuccess: () => {
      toastSuccess("Название сохранено")
      setName(null)
      refresh()
    },
    onError: () => toastError("Не удалось сохранить название"),
  })

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-14 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex items-center justify-between gap-6">
          <Label htmlFor={`name-${scope}`} className="font-normal">
            Название
          </Label>
          <Input
            id={`name-${scope}`}
            value={currentName}
            onChange={(e) => setName(e.target.value)}
            className="max-w-56"
          />
        </div>

        <div className="space-y-4 border-t pt-4">
          <AssetSlot
            scope={scope}
            asset="logo"
            label="Логотип"
            note="Показывается в шапке. PNG или WebP, отображается целиком без обрезки."
            token={map.get(`ui.${scope}.logo`) ?? ""}
            onDone={refresh}
          />
          <AssetSlot
            scope={scope}
            asset="favicon"
            label="Favicon"
            note="Иконка вкладки браузера. Квадратный PNG, лучше 32×32 или 64×64."
            token={map.get(`ui.${scope}.favicon`) ?? ""}
            onDone={refresh}
          />
        </div>
      </CardContent>
      {dirty && (
        <CardFooter className="justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => setName(null)} disabled={saveName.isPending}>
            Отменить
          </Button>
          <Button size="sm" onClick={() => saveName.mutate()} disabled={saveName.isPending}>
            {saveName.isPending && <Loader2 className="size-4 animate-spin" />}
            Сохранить
          </Button>
        </CardFooter>
      )}
    </Card>
  )
}

/**
 * Брендирование admin-панели и клиентского приложения. Логотип/favicon
 * загружаются через обычный медиа-конвейер, в настройку пишется токен —
 * знать его и вводить руками, как раньше через Raw settings, больше не нужно.
 */
export function SettingsBranding() {
  return (
    <div className="max-w-3xl space-y-4">
      <ScopeCard
        scope="admin"
        title="Admin-панель"
        description="Название и иконки этой панели — применяются к шапке, экрану входа и вкладке браузера."
      />
      <ScopeCard
        scope="client"
        title="Клиентское приложение"
        description="То же для витрины: клиент читает эти значения через публичный эндпоинт брендинга."
      />
    </div>
  )
}
