import { useState, useEffect, useMemo } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Archive, ArchiveRestore, ExternalLink, KeyRound, Plus, ShieldCheck, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/shadsnui/card"
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
import { MediaPickerDialog } from "@/components/media/MediaPickerDialog"
import { TabbedDialog, type TabDefinition } from "@/components/common/TabbedDialog"
import { KeySecretEditor } from "@/components/common/forms/KeySecretEditor"
import { LuaScriptSelect } from "@/components/common/LuaScriptSelect"
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
  extra?: Record<string, unknown>
}

interface LuaScript {
  id: number
  name: string
  kind: string
  slug?: string
}

function ProviderFormDialog({
  open,
  onOpenChange,
  provider,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  provider: Provider | null
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
      setSecretsText(isEdit ? "" : "{}")
    }
  }, [open, provider, isEdit])

  const save = useMutation({
    mutationFn: async () => {
      const trimmedSecrets = secretsText.trim()
      let secrets: unknown = undefined
      if (trimmedSecrets && trimmedSecrets !== "{}") {
        try {
          secrets = JSON.parse(trimmedSecrets)
        } catch {
          throw new Error("invalid json")
        }
      }
      const body: Record<string, unknown> = {
        title: title || null,
        enabled,
        script_id: Number(scriptId),
        scopes,
        icon_media_id: iconMediaId,
      }
      if (secrets !== undefined || !isEdit) {
        body.secrets = secrets ?? {}
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
            <Label className="text-xs">Lua-скрипт (обработка start/callback) *</Label>
            <LuaScriptSelect
              kind="auth"
              value={scriptId}
              onChange={setScriptId}
              placeholder="Выберите Lua-скрипт аутентификации"
            />
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
  const qc = useQueryClient()
  const { can } = useAuth()
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Provider | null>(null)
  const [deleting, setDeleting] = useState<Provider | null>(null)
  const [showArchived, setShowArchived] = useState(false)
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

  const toggle = useMutation({
    mutationFn: async ({ id, enabled }: { id: number; enabled: boolean }) =>
      api.patch(`/v1/admin/oauth/${id}`, { enabled }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-oauth-providers"] })
      toastSuccess("Статус провайдера обновлён")
    },
    onError: (e: unknown) => toastError("Не удалось обновить статус", getErrorDetail(e)),
  })

  const archive = useMutation({
    mutationFn: async (id: number) => api.post(`/v1/admin/oauth/${id}/archive`),
    onSuccess: () => {
      toastSuccess("OAuth-провайдер перемещён в архив")
      void qc.invalidateQueries({ queryKey: ["admin-oauth-providers"] })
    },
    onError: (e: unknown) => toastError("Не удалось архивировать провайдера", getErrorDetail(e)),
  })

  const unarchive = useMutation({
    mutationFn: async (id: number) => api.post(`/v1/admin/oauth/${id}/unarchive`),
    onSuccess: () => {
      toastSuccess("OAuth-провайдер восстановлен из архива")
      void qc.invalidateQueries({ queryKey: ["admin-oauth-providers"] })
    },
    onError: (e: unknown) => toastError("Не удалось восстановить провайдера", getErrorDetail(e)),
  })

  const filteredProviders = useMemo(
    () =>
      (data ?? []).filter((p) =>
        showArchived ? Boolean(p.extra?.is_archived) : !p.extra?.is_archived
      ),
    [data, showArchived]
  )

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">OAuth-провайдеры</h1>
          <p className="text-sm text-muted-foreground">
            Вход через социальные сети и сторонние сервисы (Google, Telegram, GitHub…).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={showArchived ? "secondary" : "outline"}
            onClick={() => setShowArchived((v) => !v)}
          >
            <Archive className="mr-1.5 size-4" />
            {showArchived ? "Активные" : "Архив"}
          </Button>
          {canCreate && (
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus className="mr-1.5 size-4" /> Добавить
            </Button>
          )}
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Загрузка провайдеров…</p>}

      {!isLoading && filteredProviders.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          {showArchived
            ? "Архив OAuth-провайдеров пуст."
            : "OAuth-провайдеры ещё не настроены."}
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filteredProviders.map((p) => {
          const s = scripts?.find((x) => x.id === p.script_id)
          return (
            <Card
              key={p.id}
              className="flex flex-col justify-between transition-colors hover:border-primary/50 cursor-pointer"
              onClick={() => canEdit && setEditing(p)}
            >
              <CardHeader className="space-y-1">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2.5 min-w-0 pr-2">
                    <div className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted/40">
                      {p.icon_url ? (
                        <img src={p.icon_url} alt="" className="size-full object-cover" />
                      ) : (
                        <ShieldCheck className="size-4 text-muted-foreground" />
                      )}
                    </div>
                    <div className="space-y-0.5 min-w-0">
                      <CardTitle className="text-base truncate">{p.title ?? p.slug}</CardTitle>
                      <p className="font-mono text-xs text-muted-foreground">{p.slug}</p>
                    </div>
                  </div>
                  <div
                    onClick={(e) => e.stopPropagation()}
                    onPointerDown={(e) => e.stopPropagation()}
                  >
                    <Switch
                      checked={p.enabled}
                      disabled={!canEdit || toggle.isPending || Boolean(p.extra?.is_archived)}
                      onCheckedChange={(v) => toggle.mutate({ id: p.id, enabled: v })}
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                <div className="flex flex-wrap items-center gap-1">
                  {p.scopes && (
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {p.scopes}
                    </Badge>
                  )}
                </div>
                <div className="text-muted-foreground">
                  Скрипт: {s ? <span className="text-foreground">{s.name ?? s.slug}</span> : <span className="italic">#{p.script_id}</span>}
                </div>
                <div
                  className="flex items-center justify-between pt-2 border-t"
                  onClick={(e) => e.stopPropagation()}
                >
                  <span className="text-[11px] text-muted-foreground inline-flex items-center gap-1 font-mono">
                    /auth/oauth/{p.slug}/callback <ExternalLink className="size-3" />
                  </span>
                  <div className="flex items-center gap-1">
                    {canEdit && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7 text-muted-foreground hover:text-foreground"
                        title={p.extra?.is_archived ? "Восстановить из архива" : "В архив"}
                        onClick={() =>
                          p.extra?.is_archived ? unarchive.mutate(p.id) : archive.mutate(p.id)
                        }
                      >
                        {p.extra?.is_archived ? (
                          <ArchiveRestore className="size-3.5" />
                        ) : (
                          <Archive className="size-3.5" />
                        )}
                      </Button>
                    )}
                    {canDelete && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7 text-destructive hover:text-destructive hover:bg-destructive/10"
                        onClick={() => setDeleting(p)}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <ProviderFormDialog
        open={creating}
        onOpenChange={setCreating}
        provider={null}
      />

      {editing && (
        <ProviderFormDialog
          open={!!editing}
          onOpenChange={(v) => !v && setEditing(null)}
          provider={editing}
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
