import { useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { KeyRound, MoreHorizontal, Plus, ShieldCheck, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
import { Card, CardContent } from "@/components/shadsnui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
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
import { TabbedDialog, type TabDefinition } from "@/components/common/TabbedDialog"
import { KeySecretEditor, COMMON_OAUTH_PRESETS } from "@/components/common/forms/KeySecretEditor"
import { toastError, toastSuccess } from "@/lib/toast"

interface Provider {
  id: number
  slug: string
  title: string | null
  enabled: boolean
  script_id: number
  scopes: string
  icon_media_id: number | null
  icon_url: string | null
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
  const [slug, setSlug] = useState("")
  const [title, setTitle] = useState("")
  const [scriptId, setScriptId] = useState("")
  const [enabled, setEnabled] = useState(false)
  const [scopes, setScopes] = useState("openid email profile")
  const [secretsText, setSecretsText] = useState("{}")
  const [iconMediaId, setIconMediaId] = useState<number | null>(null)
  const [iconUrl, setIconUrl] = useState<string | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const qc = useQueryClient()

  useEffect(() => {
    if (open) {
      setSlug(provider?.slug ?? "")
      setTitle(provider?.title ?? "")
      setScriptId(provider?.script_id ? String(provider.script_id) : "")
      setEnabled(provider?.enabled ?? false)
      setScopes(provider?.scopes ?? "openid email profile")
      setIconMediaId(provider?.icon_media_id ?? null)
      setIconUrl(provider?.icon_url ?? null)
      setSecretsText("{}")
    }
  }, [open, provider])

  const selectedScript = authScripts?.find((s) => String(s.id) === scriptId)

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

  const tabs: TabDefinition[] = [
    {
      id: "general",
      label: "Основное",
      icon: ShieldCheck,
      content: (
        <div className="space-y-4">
          <div className="flex items-center gap-3 rounded-lg border border-border/60 bg-muted/20 p-2.5">
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-background hover:border-primary transition-colors cursor-pointer"
              title="Выбрать иконку из медиаархива"
            >
              {iconUrl ? (
                <img src={iconUrl} alt="" className="size-full object-cover" />
              ) : (
                <ShieldCheck className="size-5 text-muted-foreground" />
              )}
            </button>
            <div className="space-y-0.5">
              <p className="text-xs font-medium">Иконка OAuth-провайдера</p>
              <p className="text-[10px] text-muted-foreground">
                Отображается на кнопке входа для пользователей
              </p>
              {iconUrl && (
                <button
                  type="button"
                  onClick={() => {
                    setIconMediaId(null)
                    setIconUrl(null)
                  }}
                  className="text-[10px] text-destructive hover:underline cursor-pointer"
                >
                  Удалить иконку
                </button>
              )}
            </div>
          </div>

          {!isEdit && (
            <div className="space-y-1.5">
              <Label className="text-xs">Слаг провайдера (уникальный ключ)</Label>
              <Input
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="google"
                autoFocus
                className="font-mono text-xs"
              />
              <p className="text-[10px] text-muted-foreground">Используется в URL роутинге, например `/auth/oauth/google`</p>
            </div>
          )}

          <div className="space-y-1.5">
            <Label className="text-xs">Отображаемое название</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Google (Вход через аккаунт)"
              className="text-xs"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Lua-скрипт (обработка start/callback)</Label>
            <Select value={scriptId} onValueChange={(v) => setScriptId(v ?? "")}>
              <SelectTrigger className="text-xs">
                <SelectValue placeholder="Выберите Lua-скрипт">
                  {selectedScript ? selectedScript.name : undefined}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {authScripts?.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)} className="text-xs">
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {(authScripts?.length ?? 0) === 0 && (
              <p className="text-xs text-muted-foreground">
                Нет скриптов типа «auth» — создайте их на странице «Lua-скрипты».
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Запрашиваемые права (OAuth Scopes)</Label>
            <Input
              value={scopes}
              onChange={(e) => setScopes(e.target.value)}
              className="font-mono text-xs"
              placeholder="openid email profile"
            />
          </div>

          <div className="flex h-9 items-center justify-between rounded-md border border-input bg-background px-3 py-1">
            <div>
              <span className="text-xs font-medium">Статус провайдера</span>
              <p className="text-[10px] text-muted-foreground">Разрешить вход через этот сервис</p>
            </div>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>
        </div>
      ),
    },
    {
      id: "secrets",
      label: "Ключи и секреты",
      icon: KeyRound,
      badge: isEdit ? "Зашифровано" : undefined,
      content: (
        <div className="space-y-3">
          <KeySecretEditor
            title="OAuth Client Credentials"
            description={
              isEdit
                ? "Оставьте значения пустыми или {}, если не хотите менять сохранённые ключи"
                : "Укажите client_id, client_secret и адреса эндпоинтов"
            }
            presets={COMMON_OAUTH_PRESETS}
            value={secretsText}
            onChange={(_, text) => setSecretsText(text)}
          />
        </div>
      ),
    },
  ]

  return (
    <>
      <TabbedDialog
        open={open}
        onOpenChange={onOpenChange}
        title={isEdit ? `OAuth «${provider?.title || provider?.slug}»` : "Новый OAuth-провайдер"}
        description="Настройка внешней авторизации и входа через соцсети"
        tabs={tabs}
        primaryAction={{
          label: isEdit ? "Сохранить изменения" : "Создать провайдера",
          onClick: () => save.mutate(),
          disabled: (!isEdit && slug.trim().length < 2) || !scriptId || save.isPending,
          loading: save.isPending,
        }}
        secondaryAction={{
          label: "Отмена",
          onClick: () => onOpenChange(false),
        }}
      />

      <MediaPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onSelect={(m) => {
          setIconMediaId(m.id)
          setIconUrl(m.url)
        }}
      />
    </>
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
        <div>
          <h1 className="text-xl font-semibold">OAuth-провайдеры</h1>
          <p className="text-sm text-muted-foreground">
            Вход через социальные сети и сторонние сервисы (Google, Telegram, GitHub…).
          </p>
        </div>
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
            OAuth-провайдеры ещё не настроены.
          </CardContent>
        </Card>
      )}

      <div className="grid gap-2">
        {data?.map((p) => (
          <Card key={p.id}>
            <CardContent className="flex items-center justify-between gap-3 py-3">
              <div className="flex items-center gap-3">
                <div className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
                  {p.icon_url ? (
                    <img src={p.icon_url} alt="" className="size-full object-cover" />
                  ) : (
                    <ShieldCheck className="size-4 text-muted-foreground" />
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{p.title ?? p.slug}</span>
                    <span className="font-mono text-xs text-muted-foreground">{p.slug}</span>
                    <Badge variant={p.enabled ? "default" : "outline"}>
                      {p.enabled ? "включён" : "выключен"}
                    </Badge>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Scopes: <span className="font-mono">{p.scopes}</span>
                    {` · Lua-скрипт #${p.script_id}`}
                  </p>
                </div>
              </div>

              {(canEdit || canDelete) && (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button variant="ghost" size="icon" className="size-8">
                        <MoreHorizontal className="size-4" />
                      </Button>
                    }
                  />
                  <DropdownMenuContent align="end">
                    {canEdit && (
                      <DropdownMenuItem onClick={() => setEditing(p)}>Изменить</DropdownMenuItem>
                    )}
                    {canDelete && (
                      <DropdownMenuItem
                        onClick={() => setDeleting(p)}
                        className="text-destructive focus:text-destructive"
                      >
                        <Trash2 className="size-4 mr-1.5" /> Удалить
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <ProviderFormDialog
        open={creating}
        onOpenChange={setCreating}
        provider={null}
        authScripts={authScripts}
      />

      {editing && (
        <ProviderFormDialog
          open={!!editing}
          onOpenChange={(v) => !v && setEditing(null)}
          provider={editing}
          authScripts={authScripts}
        />
      )}

      {deleting && (
        <DeleteProviderDialog
          provider={deleting}
          open={!!deleting}
          onOpenChange={(v) => !v && setDeleting(null)}
        />
      )}
    </div>
  )
}
