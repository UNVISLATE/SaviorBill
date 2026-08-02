import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, UploadCloud } from "lucide-react"

import { api } from "@/api/api.ts"
import { uploadOwnMedia } from "@/api/media-upload.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { Field, FieldDescription, FieldLabel } from "@/components/shadsnui/field"
import { Input } from "@/components/shadsnui/input"
import { Separator } from "@/components/shadsnui/separator"
import { Skeleton } from "@/components/shadsnui/skeleton"

interface SettingRawOut {
  key: string
  value: string | null
}

interface Page<T> {
  items: T[]
}

function mediaUrl(token: string | null | undefined): string | null {
  return token ? `/api/media/${token}` : null
}

/** Загрузка+привязка логотипа/favicon одного scope ("admin"|"client"). */
function ImagePicker({
  scope,
  field,
  label,
  currentToken,
  onUploaded,
}: {
  scope: "admin" | "client"
  field: "logo" | "favicon"
  label: string
  currentToken: string | null | undefined
  onUploaded: () => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<string | null>(null)

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const { token } = await uploadOwnMedia(file, { tag: `${scope}-${field}` })
      await api.post(`/v1/admin/settings/ui/${scope}.${field}`, { value: token })
      return token
    },
    onSuccess: () => {
      toastSuccess(`${label} обновлён`)
      setPreview(null)
      onUploaded()
    },
    onError: (err: unknown) =>
      toastError(
        `Не удалось загрузить ${label.toLowerCase()}`,
        err instanceof Error ? err.message : undefined,
      ),
  })

  function pick(file: File | undefined) {
    if (!file) return
    setPreview(URL.createObjectURL(file))
    upload.mutate(file)
  }

  const shownUrl = preview ?? mediaUrl(currentToken)

  return (
    <Field>
      <FieldLabel>{label}</FieldLabel>
      <div className="flex items-center gap-3">
        <div className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted/40">
          {shownUrl ? (
            <img src={shownUrl} alt="" className="size-full object-contain" />
          ) : (
            <UploadCloud className="size-5 text-muted-foreground" />
          )}
        </div>
        <div className="flex flex-col gap-1">
          <Button
            size="sm"
            variant="outline"
            disabled={upload.isPending}
            onClick={() => inputRef.current?.click()}
          >
            {upload.isPending && <Loader2 className="size-4 animate-spin" />}
            Загрузить файл
          </Button>
          <FieldDescription>PNG/WebP, без обрезки — целиком, без кропа.</FieldDescription>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            pick(e.target.files?.[0])
            e.target.value = ""
          }}
        />
      </div>
    </Field>
  )
}

function ScopeSection({ scope, title }: { scope: "admin" | "client"; title: string }) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ["admin-settings-ui", scope],
    queryFn: async () =>
      (
        await api.get<Page<SettingRawOut>>("/v1/admin/settings/raw", {
          params: { group: "ui", limit: 100, q: `ui.${scope}.` },
        })
      ).data.items,
  })
  const [name, setName] = useState<string | null>(null)

  const byKey = (suffix: string) => data?.find((r) => r.key === `ui.${scope}.${suffix}`)?.value ?? null

  const currentName = name ?? byKey("name") ?? ""

  const saveName = useMutation({
    mutationFn: async () => api.post(`/v1/admin/settings/ui/${scope}.name`, { value: currentName }),
    onSuccess: () => {
      toastSuccess("Название сохранено")
      void qc.invalidateQueries({ queryKey: ["admin-settings-ui", scope] })
    },
    onError: () => toastError("Не удалось сохранить название"),
  })

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin-settings-ui", scope] })
  }

  if (isLoading) {
    return (
      <section className="space-y-4">
        <h3 className="text-sm font-semibold">{title}</h3>
        <Skeleton className="h-24 w-full" />
      </section>
    )
  }

  return (
    <section className="space-y-4">
      <h3 className="text-sm font-semibold">{title}</h3>
      <Field>
        <FieldLabel>Название</FieldLabel>
        <div className="flex gap-2">
          <Input value={currentName} onChange={(e) => setName(e.target.value)} />
          <Button
            size="sm"
            variant="outline"
            disabled={saveName.isPending || currentName === (byKey("name") ?? "")}
            onClick={() => saveName.mutate()}
          >
            Сохранить
          </Button>
        </div>
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <ImagePicker scope={scope} field="logo" label="Логотип" currentToken={byKey("logo")} onUploaded={refresh} />
        <ImagePicker scope={scope} field="favicon" label="Favicon" currentToken={byKey("favicon")} onUploaded={refresh} />
      </div>
    </section>
  )
}

/**
 * Брендирование admin-панели и клиентского приложения — раньше это была
 * пара строк, которые приходилось находить и редактировать в Raw settings
 * вручную (см. PLAN.md). Здесь же — то, чего до этой страницы не было
 * вообще: сама admin-панель теперь ЧИТАЕТ эти настройки (см.
 * `hooks/use-branding.ts`, `App.tsx`) — раньше `ui.admin.*` можно было
 * поменять через API, но интерфейс всё равно продолжал показывать
 * захардкоженные "SaviorBill Admin"/статичный логотип.
 */
export function SettingsBranding() {
  return (
    <div className="max-w-2xl space-y-8">
      <p className="text-sm text-muted-foreground">
        Изменения вступают в силу в открытых вкладках в течение минуты
        (кэш браузера/ETag) — обычно достаточно обновить страницу.
      </p>
      <ScopeSection scope="admin" title="Admin-панель" />
      <Separator />
      <ScopeSection scope="client" title="Клиентское приложение" />
    </div>
  )
}
