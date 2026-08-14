import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MoreHorizontal, Plus, ShieldCheck, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
import { Textarea } from "@/components/shadsnui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import { Card, CardContent } from "@/components/shadsnui/card"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/shadsnui/alert-dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/shadsnui/dropdown-menu"
import { MediaPickerDialog } from "@/components/media/MediaPickerDialog"
import { toastError, toastSuccess } from "@/lib/toast"

interface Provider {
  id: number
  slug: string
  title: string | null
  enabled: boolean
  script_id: number | null
  script_version: number | null
  icon_media_id: number | null
  icon_url: string | null
  scopes: string
  extra: Record<string, unknown>
}

interface LuaScript {
  id: number
  name: string
  kind: string
}

function ProviderFormDialog({
  open,
  onOpenChange,
  provider,
  authScripts,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  provider: Provider | null
  authScripts: LuaScript[] | undefined
}) {
  const isEdit = !!provider
  const [slug, setSlug] = useState(provider?.slug ?? "")
  const [title, setTitle] = useState(provider?.title ?? "")
  const [scriptId, setScriptId] = useState(provider?.script_id ? String(provider.script_id) : "")
  const [enabled, setEnabled] = useState(provider?.enabled ?? false)
  const [scopes, setScopes] = useState(provider?.scopes ?? "openid email profile")
  const [secretsText, setSecretsText] = useState("{}")
  const [iconMediaId, setIconMediaId] = useState<number | null>(provider?.icon_media_id ?? null)
  const [iconUrl, setIconUrl] = useState<string | null>(provider?.icon_url ?? null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const qc = useQueryClient()

  const save = useMutation({
    mutationFn: async () => {
      let secrets: unknown = {}
      if (secretsText.trim()) {
        try {
          secrets = JSON.parse(secretsText)
        } catch {
          throw new Error("invalid json")
        }
      }
      const body = {
        title: title || null,
        enabled,
        script_id: Number(scriptId),
        scopes,
        secrets,
        icon_media_id: iconMediaId,
      }
      if (isEdit) return api.patch(`/v1/admin/oauth/${provider!.id}`, body)
      return api.post("/v1/admin/oauth", { ...body, slug })
    },
    onSuccess: () => {
      toastSuccess(isEdit ? "Провайдер обновлён" : "Провайдер создан")
      onOpenChange(false)
      void qc.invalidateQueries({ queryKey: ["admin-oauth-providers"] })
    },
    onError: (e: unknown) =>
      toastError(
        isEdit ? "Не удалось обновить провайдера" : "Не удалось создать провайдера",
        (e as Error).message === "invalid json" ? "secrets должен быть корректным JSON" : getErrorDetail(e),
      ),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Изменить OAuth-провайдера" : "Новый OAuth-провайдер"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted"
            >
              {iconUrl ? <img src={iconUrl} alt="" className="size-full object-cover" /> : <ShieldCheck className="size-5 text-muted-foreground" />}
            </button>
            <p className="text-xs text-muted-foreground">Иконка провайдера (опционально)</p>
          </div>
          {!isEdit && (
            <div className="space-y-1">
              <Label>Слаг</Label>
              <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="google" autoFocus />
            </div>
          )}
          <div className="space-y-1">
            <Label>Название</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Google" />
          </div>
          <div className="space-y-1">
            <Label>Auth-скрипт (обрабатывает start/callback)</Label>
            <Select value={scriptId} onValueChange={(v) => setScriptId(v ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder="Выберите скрипт" />
              </SelectTrigger>
              <SelectContent>
                {authScripts?.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {(authScripts?.length ?? 0) === 0 && (
              <p className="text-xs text-muted-foreground">
                Нет скриптов типа «auth» — создайте на странице «Скрипты».
              </p>
            )}
          </div>
          <div className="space-y-1">
            <Label>Scopes</Label>
            <Input value={scopes} onChange={(e) => setScopes(e.target.value)} />
          </div>
          <div className="flex items-center justify-between">
            <Label>Включён</Label>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>
          <div className="space-y-1">
            <Label>Секреты (JSON: client_id, client_secret и т.п., шифруются на сервере)</Label>
            <Textarea
              className="font-mono text-xs"
              rows={4}
              value={secretsText}
              onChange={(e) => setSecretsText(e.target.value)}
              placeholder={isEdit ? "Оставьте {} чтобы не менять" : '{"client_id": "...", "client_secret": "..."}'}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            disabled={(!isEdit && slug.trim().length < 2) || !scriptId || save.isPending}
            onClick={() => save.mutate()}
          >
            {isEdit ? "Сохранить" : "Создать"}
          </Button>
        </DialogFooter>
        <MediaPickerDialog
          open={pickerOpen}
          onOpenChange={setPickerOpen}
          onSelect={(m) => {
            setIconMediaId(m.id)
            setIconUrl(m.url)
          }}
        />
      </DialogContent>
    </Dialog>
  )
}

function DeleteProviderDialog({
  provider,
  open,
  onOpenChange,
}: {
  provider: Provider
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const del = useMutation({
    mutationFn: async () => api.delete(`/v1/admin/oauth/${provider.id}`),
    onSuccess: () => {
      toastSuccess(`Провайдер «${provider.title ?? provider.slug}» удалён`)
      onOpenChange(false)
      void qc.invalidateQueries({ queryKey: ["admin-oauth-providers"] })
    },
    onError: (e: unknown) => toastError("Не удалось удалить провайдера", getErrorDetail(e)),
  })

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Удалить провайдера «{provider.title ?? provider.slug}»?</AlertDialogTitle>
          <AlertDialogDescription>
            Привязки пользователей к этому провайдеру останутся, но вход через него станет недоступен.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Отмена</AlertDialogCancel>
          <AlertDialogAction
            disabled={del.isPending}
            onClick={() => del.mutate()}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            Удалить
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export function OAuthProvidersPage() {
  const { can } = useAuth()
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Provider | null>(null)
  const [deleting, setDeleting] = useState<Provider | null>(null)

  const canCreate = can("oauth.create")
  const canEdit = can("oauth.edit")
  const canDelete = can("oauth.delete")

  const { data, isLoading } = useQuery({
    queryKey: ["admin-oauth-providers"],
    queryFn: async () => (await api.get<Provider[]>("/v1/admin/oauth")).data,
  })

  const { data: scripts } = useQuery({
    queryKey: ["admin-lua-scripts-lookup"],
    queryFn: async () => (await api.get<LuaScript[]>("/v1/admin/lua")).data,
    staleTime: 60_000,
  })
  const authScripts = scripts?.filter((s) => s.kind === "auth")

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Вход через OAuth</h1>
        {canCreate && (
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="size-4" /> Добавить провайдера
          </Button>
        )}
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
      {!isLoading && (data?.length ?? 0) === 0 && (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            OAuth-провайдеры ещё не настроены. Вход по паролю продолжит работать как обычно.
          </CardContent>
        </Card>
      )}

      <div className="grid gap-2">
        {data?.map((p) => (
          <Card key={p.id}>
            <CardContent className="flex items-center justify-between gap-3 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
                  {p.icon_url ? (
                    <img src={p.icon_url} alt="" className="size-full object-cover" />
                  ) : (
                    <ShieldCheck className="size-4 text-muted-foreground" />
                  )}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{p.title ?? p.slug}</span>
                    <span className="font-mono text-xs text-muted-foreground">{p.slug}</span>
                    <Badge variant={p.enabled ? "default" : "outline"}>{p.enabled ? "включён" : "выключен"}</Badge>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{p.scopes}</p>
                </div>
              </div>
              {(canEdit || canDelete) && (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button variant="ghost" size="icon" className="size-8 shrink-0">
                        <MoreHorizontal className="size-4" />
                      </Button>
                    }
                  />
                  <DropdownMenuContent align="end">
                    {canEdit && <DropdownMenuItem onClick={() => setEditing(p)}>Изменить</DropdownMenuItem>}
                    {canDelete && (
                      <DropdownMenuItem variant="destructive" onClick={() => setDeleting(p)}>
                        <Trash2 className="size-4" /> Удалить
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <ProviderFormDialog open={creating} onOpenChange={setCreating} provider={null} authScripts={authScripts} />
      {editing && (
        <ProviderFormDialog
          open={!!editing}
          onOpenChange={(v) => !v && setEditing(null)}
          provider={editing}
          authScripts={authScripts}
        />
      )}
      {deleting && (
        <DeleteProviderDialog provider={deleting} open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)} />
      )}
    </div>
  )
}
