import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  Bot,
  Calendar,
  Check,
  Clock,
  Copy,
  Globe,
  KeyRound,
  Plus,
  Shield,
  Trash2,
  User,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth.tsx"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { Badge } from "@/components/shadsnui/badge"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Textarea } from "@/components/shadsnui/textarea"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { TabbedDialog, type TabDefinition } from "@/components/common/TabbedDialog"
import { PermsPicker, type PermsCatalog } from "@/components/common/PermsPicker"

interface AppToken {
  id: number
  name: string
  description: string | null
  token_prefix: string
  permissions: string[]
  ip_allowlist: string[] | null
  created_by_account_id: number | null
  created_by_login: string | null
  created_at: string
  expires_at: string | null
  last_used_at: string | null
  last_used_ip: string | null
  is_revoked: boolean
  revoked_at: string | null
}

interface AppTokenCreated extends AppToken {
  secret_token: string
}

export function AppTokensSettings() {
  const qc = useQueryClient()
  const { me, can } = useAuth()
  const isOwner = me?.role === "owner"
  const canManageAny = can("apptokens.manage_any")

  const [createOpen, setCreateOpen] = useState(false)
  const [revealedToken, setRevealedToken] = useState<AppTokenCreated | null>(null)
  const [copiedSecret, setCopiedSecret] = useState(false)

  // Details Modal
  const [viewingToken, setViewingToken] = useState<AppToken | null>(null)
  const [copiedPrefix, setCopiedPrefix] = useState(false)

  // Creation form state
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [ipAllowlistRaw, setIpAllowlistRaw] = useState("")

  // Flexible expiration: "never" | "days" | "date"
  const [expiryType, setExpiryType] = useState<"never" | "days" | "date">("never")
  const [expiryDaysInput, setExpiryDaysInput] = useState<string>("30")
  const [expiryDateInput, setExpiryDateInput] = useState<string>("")

  // RBAC permissions tree state
  const [selectedPerms, setSelectedPerms] = useState<Set<string>>(new Set())

  // Confirmations
  const [revokingToken, setRevokingToken] = useState<AppToken | null>(null)
  const [deletingToken, setDeletingToken] = useState<AppToken | null>(null)

  // Queries
  const { data: tokens = [], isLoading } = useQuery({
    queryKey: ["admin-app-tokens"],
    queryFn: async () => (await api.get<AppToken[]>("/v1/admin/app-tokens")).data,
  })

  const { data: permsCatalog } = useQuery({
    queryKey: ["admin-perms"],
    queryFn: async () => (await api.get<PermsCatalog>("/v1/admin/perms")).data,
  })

  // Защита от эскалации привилегий: пользователь может делегировать только свои права
  const availablePerms = useMemo(() => {
    if (isOwner) return undefined
    const flat = permsCatalog?.flat ?? []
    return new Set(flat.filter((p) => can(p)))
  }, [isOwner, permsCatalog, can])

  const canManageToken = (token: AppToken) => {
    if (isOwner || canManageAny) return true
    return token.created_by_account_id === me?.id
  }

  const createMutation = useMutation({
    mutationFn: async () => {
      let expires_at: string | null = null

      if (expiryType === "days") {
        const days = parseInt(expiryDaysInput, 10)
        if (isNaN(days) || days <= 0) {
          throw new Error("Укажите корректное количество дней")
        }
        const d = new Date()
        d.setDate(d.getDate() + days)
        expires_at = d.toISOString()
      } else if (expiryType === "date") {
        if (!expiryDateInput) {
          throw new Error("Выберите дату окончания действия")
        }
        const d = new Date(expiryDateInput)
        if (isNaN(d.getTime())) {
          throw new Error("Некорректная дата окончания")
        }
        expires_at = d.toISOString()
      }

      const ipList = ipAllowlistRaw
        .split(/[\n,]/)
        .map((s) => s.trim())
        .filter(Boolean)

      const payload = {
        name: name.trim(),
        description: description.trim() || null,
        permissions: Array.from(selectedPerms),
        ip_allowlist: ipList.length > 0 ? ipList : null,
        expires_at,
      }

      return (await api.post<AppTokenCreated>("/v1/admin/app-tokens", payload)).data
    },
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["admin-app-tokens"] })
      setCreateOpen(false)
      resetForm()
      setRevealedToken(created)
      toastSuccess("Токен приложения успешно выпущен")
    },
    onError: (err: any) => {
      toastError(err?.response?.data?.detail || err?.message || "Не удалось создать токен")
    },
  })

  const revokeMutation = useMutation({
    mutationFn: async (id: number) => {
      await api.post(`/v1/admin/app-tokens/${id}/revoke`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-app-tokens"] })
      setRevokingToken(null)
      if (viewingToken) {
        setViewingToken((prev) => (prev ? { ...prev, is_revoked: true, revoked_at: new Date().toISOString() } : null))
      }
      toastSuccess("Токен отозван")
    },
    onError: (err: any) => {
      toastError(err?.response?.data?.detail || "Не удалось отозвать токен")
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/v1/admin/app-tokens/${id}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-app-tokens"] })
      setDeletingToken(null)
      setViewingToken(null)
      toastSuccess("Токен удален")
    },
    onError: (err: any) => {
      toastError(err?.response?.data?.detail || "Не удалось удалить токен")
    },
  })

  const resetForm = () => {
    setName("")
    setDescription("")
    setIpAllowlistRaw("")
    setExpiryType("never")
    setExpiryDaysInput("30")
    setExpiryDateInput("")
    setSelectedPerms(new Set())
  }

  const handleCopySecret = () => {
    if (!revealedToken) return
    navigator.clipboard.writeText(revealedToken.secret_token)
    setCopiedSecret(true)
    toastSuccess("Секретный токен скопирован в буфер обмена")
    setTimeout(() => setCopiedSecret(false), 3000)
  }

  const handleCopyPrefix = (prefix: string) => {
    navigator.clipboard.writeText(prefix)
    setCopiedPrefix(true)
    toastSuccess("Префикс токена скопирован")
    setTimeout(() => setCopiedPrefix(false), 2000)
  }

  const createTabs: TabDefinition[] = [
    {
      id: "general",
      label: "Основные параметры",
      icon: Bot,
      content: (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Название токена / сервиса *</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Например: Telegram Shop Bot, CRM Gateway"
              className="text-xs"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Описание назначения (опционально)</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Для чего используется данный токен..."
              rows={2}
              className="text-xs resize-none"
            />
          </div>

          {/* Expiration Configuration */}
          <div className="space-y-2 rounded-lg border border-border/60 bg-muted/20 p-3">
            <Label className="text-xs flex items-center gap-1.5 font-medium">
              <Calendar className="size-3.5 text-primary" /> Срок действия ключа
            </Label>

            <div className="grid grid-cols-3 gap-2">
              <Button
                type="button"
                variant={expiryType === "never" ? "default" : "outline"}
                size="sm"
                onClick={() => setExpiryType("never")}
                className="text-xs h-8"
              >
                Бессрочно
              </Button>
              <Button
                type="button"
                variant={expiryType === "days" ? "default" : "outline"}
                size="sm"
                onClick={() => setExpiryType("days")}
                className="text-xs h-8"
              >
                Количество дней
              </Button>
              <Button
                type="button"
                variant={expiryType === "date" ? "default" : "outline"}
                size="sm"
                onClick={() => setExpiryType("date")}
                className="text-xs h-8"
              >
                Точная дата
              </Button>
            </div>

            {expiryType === "days" && (
              <div className="pt-1.5 space-y-1">
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    min={1}
                    max={3650}
                    value={expiryDaysInput}
                    onChange={(e) => setExpiryDaysInput(e.target.value)}
                    placeholder="30"
                    className="h-8 text-xs font-mono w-28"
                  />
                  <span className="text-xs text-muted-foreground">дней с момента создания</span>
                </div>
                <div className="flex gap-1.5 pt-1">
                  {[7, 30, 90, 180, 365].map((d) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => setExpiryDaysInput(String(d))}
                      className="text-[10px] px-2 py-0.5 rounded bg-muted hover:bg-muted/80 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      +{d}д
                    </button>
                  ))}
                </div>
              </div>
            )}

            {expiryType === "date" && (
              <div className="pt-1.5 space-y-1">
                <Input
                  type="datetime-local"
                  min={new Date().toISOString().slice(0, 16)}
                  value={expiryDateInput}
                  onChange={(e) => setExpiryDateInput(e.target.value)}
                  className="h-8 text-xs font-mono"
                />
                <p className="text-[10px] text-muted-foreground">
                  Токен будет автоматически деактивирован в указанное время.
                </p>
              </div>
            )}

            {expiryType === "never" && (
              <p className="text-[11px] text-muted-foreground pt-0.5">
                Ключ будет оставаться активным бессрочно до ручного отзыва.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs flex items-center gap-1.5">
              <Globe className="size-3.5 text-muted-foreground" /> Белый список IP / CIDR (опционально)
            </Label>
            <Textarea
              value={ipAllowlistRaw}
              onChange={(e) => setIpAllowlistRaw(e.target.value)}
              placeholder="192.168.1.10&#10;10.0.0.0/24&#10;(по одному на строку или через запятую; пусто = любые IP)"
              rows={2}
              className="font-mono text-xs resize-none"
            />
            <p className="text-[10px] text-muted-foreground">
              Если указан — запросы с других IP-адресов будут отсекаться с кодом 403 Forbidden.
            </p>
          </div>
        </div>
      ),
    },
    {
      id: "permissions",
      label: "Права доступа (RBAC)",
      icon: Shield,
      badge: `${selectedPerms.size}`,
      content: (
        <div className="space-y-2">
          {!isOwner && (
            <p className="text-[11px] text-muted-foreground bg-muted/30 px-2.5 py-1.5 rounded border border-border/40">
              Вам доступны для выдачи только те права, которыми обладает ваша учетная запись.
            </p>
          )}
          <PermsPicker
            selected={selectedPerms}
            onChange={setSelectedPerms}
            catalog={permsCatalog}
            availablePerms={availablePerms}
            maxHeight="max-h-[340px]"
          />
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Токены приложений (App Tokens)</h2>
          <p className="text-xs text-muted-foreground">
            Постоянные API-ключи со Scoped RBAC для ботов, внешних сайтов и микросервисов.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)} className="gap-1.5 text-xs">
          <Plus className="size-4" /> Выпустить токен
        </Button>
      </div>

      {/* Table */}
      <div className="rounded-lg border border-border/60 bg-card overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[180px]">Приложение / Название</TableHead>
              <TableHead>Префикс токена</TableHead>
              {canManageAny && <TableHead>Создатель</TableHead>}
              <TableHead>Права (Scoped RBAC)</TableHead>
              <TableHead>IP доступ</TableHead>
              <TableHead>Срок действия</TableHead>
              <TableHead>Посл. использование</TableHead>
              <TableHead className="text-right">Действия</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={canManageAny ? 8 : 7} className="text-center py-8 text-xs text-muted-foreground">
                  Загрузка токенов...
                </TableCell>
              </TableRow>
            ) : tokens.length === 0 ? (
              <TableRow>
                <TableCell colSpan={canManageAny ? 8 : 7} className="text-center py-12 text-muted-foreground">
                  <div className="flex flex-col items-center gap-2">
                    <KeyRound className="size-8 text-muted-foreground/40" />
                    <p className="text-sm font-medium">Нет активных токенов приложений</p>
                    <p className="text-xs text-muted-foreground/80">
                      Выпустите первый токен для интеграции с ботом или внешней CRM.
                    </p>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setCreateOpen(true)}
                      className="mt-2 text-xs"
                    >
                      <Plus className="size-3.5 mr-1" /> Создать токен
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              tokens.map((token) => {
                const isExpired = token.expires_at && new Date(token.expires_at) < new Date()
                const canManage = canManageToken(token)

                return (
                  <TableRow
                    key={token.id}
                    onClick={() => setViewingToken(token)}
                    className={`cursor-pointer transition-colors hover:bg-muted/50 ${
                      token.is_revoked ? "opacity-60 bg-muted/20" : ""
                    }`}
                  >
                    <TableCell>
                      <div className="space-y-0.5">
                        <div className="font-medium text-xs flex items-center gap-1.5">
                          <Bot className="size-3.5 text-primary/80" />
                          {token.name}
                        </div>
                        {token.description && (
                          <p className="text-[11px] text-muted-foreground line-clamp-1">
                            {token.description}
                          </p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className="font-mono text-xs font-semibold tracking-wider text-foreground bg-muted/30"
                      >
                        {token.token_prefix}
                      </Badge>
                    </TableCell>

                    {canManageAny && (
                      <TableCell className="text-xs">
                        {token.created_by_login ? (
                          <span className="font-medium text-foreground">@{token.created_by_login}</span>
                        ) : token.created_by_account_id ? (
                          <span className="text-muted-foreground">#{token.created_by_account_id}</span>
                        ) : (
                          <span className="text-muted-foreground">система</span>
                        )}
                      </TableCell>
                    )}

                    <TableCell>
                      <div className="flex flex-wrap gap-1 max-w-[220px]">
                        {token.permissions.length === 0 ? (
                          <span className="text-[11px] text-muted-foreground">Нет прав</span>
                        ) : (
                          <>
                            {token.permissions.slice(0, 2).map((p) => (
                              <Badge key={p} variant="secondary" className="text-[10px] py-0 font-mono">
                                {p}
                              </Badge>
                            ))}
                            {token.permissions.length > 2 && (
                              <Badge variant="outline" className="text-[10px] py-0">
                                +{token.permissions.length - 2}
                              </Badge>
                            )}
                          </>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      {token.ip_allowlist && token.ip_allowlist.length > 0 ? (
                        <Badge variant="secondary" className="text-[10px]">
                          {token.ip_allowlist.length} IP
                        </Badge>
                      ) : (
                        <span className="text-[11px] text-muted-foreground">Все IP</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {token.is_revoked ? (
                        <Badge variant="destructive" className="text-[10px]">Отозван</Badge>
                      ) : isExpired ? (
                        <Badge variant="destructive" className="text-[10px]">Истек</Badge>
                      ) : token.expires_at ? (
                        <span className="text-xs text-muted-foreground">
                          до {new Date(token.expires_at).toLocaleDateString()}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">Бессрочный</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="text-xs">
                        {token.last_used_at ? (
                          <>
                            <div>{new Date(token.last_used_at).toLocaleDateString()}</div>
                            <div className="text-[10px] text-muted-foreground font-mono">
                              {token.last_used_ip || "—"}
                            </div>
                          </>
                        ) : (
                          <span className="text-muted-foreground text-[11px]">Никогда</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div
                        className="flex items-center justify-end gap-1"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {canManage ? (
                          <>
                            {!token.is_revoked && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setRevokingToken(token)}
                                className="h-7 text-xs text-amber-500 hover:text-amber-400 hover:bg-amber-500/10"
                              >
                                Отозвать
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => setDeletingToken(token)}
                              className="size-7 text-destructive hover:bg-destructive/10"
                            >
                              <Trash2 className="size-3.5" />
                            </Button>
                          </>
                        ) : (
                          <span className="text-[10px] text-muted-foreground italic px-2">
                            чужой токен
                          </span>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>

      {/* Creation Dialog */}
      <TabbedDialog
        open={createOpen}
        onOpenChange={(v) => {
          setCreateOpen(v)
          if (!v) resetForm()
        }}
        title="Выпуск токена приложения"
        description="Создание постоянного API-ключа с изолированными правами доступа"
        tabs={createTabs}
        primaryAction={{
          label: "Сгенерировать токен",
          onClick: () => createMutation.mutate(),
          loading: createMutation.isPending,
          disabled: !name.trim(),
        }}
      />

      {/* Details View Modal */}
      <Dialog open={viewingToken !== null} onOpenChange={(open) => !open && setViewingToken(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          {viewingToken && (
            <>
              <DialogHeader>
                <div className="flex items-center justify-between gap-3 pr-6">
                  <DialogTitle className="flex items-center gap-2 text-base font-semibold">
                    <Bot className="size-5 text-primary" />
                    {viewingToken.name}
                  </DialogTitle>
                  <div>
                    {viewingToken.is_revoked ? (
                      <Badge variant="destructive">Отозван</Badge>
                    ) : viewingToken.expires_at && new Date(viewingToken.expires_at) < new Date() ? (
                      <Badge variant="destructive">Срок истек</Badge>
                    ) : (
                      <Badge variant="default" className="bg-emerald-600 hover:bg-emerald-600 text-white">
                        Активен
                      </Badge>
                    )}
                  </div>
                </div>
                <DialogDescription>
                  Информация о токене приложения, параметрах доступа и назначенных правах
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4 py-2 text-xs">
                {/* Description if present */}
                {viewingToken.description && (
                  <div className="p-3 rounded-lg border border-border/60 bg-muted/20 text-muted-foreground">
                    {viewingToken.description}
                  </div>
                )}

                {/* Key attributes grid */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg border border-border/60 bg-muted/10 space-y-1.5">
                    <span className="text-[11px] text-muted-foreground font-medium block">
                      Префикс идентификации
                    </span>
                    <div className="flex items-center justify-between gap-2">
                      <code className="font-mono text-xs font-semibold px-2 py-0.5 rounded bg-muted/60 text-foreground">
                        {viewingToken.token_prefix}
                      </code>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-6 px-1.5 text-[11px]"
                        onClick={() => handleCopyPrefix(viewingToken.token_prefix)}
                      >
                        {copiedPrefix ? <Check className="size-3 text-emerald-500 mr-1" /> : <Copy className="size-3 mr-1" />}
                        {copiedPrefix ? "Скопировано" : "Копировать"}
                      </Button>
                    </div>
                  </div>

                  <div className="p-3 rounded-lg border border-border/60 bg-muted/10 space-y-1.5">
                    <span className="text-[11px] text-muted-foreground font-medium block">
                      Создатель токена
                    </span>
                    <div className="flex items-center gap-1.5 text-foreground font-medium">
                      <User className="size-3.5 text-muted-foreground" />
                      {viewingToken.created_by_login ? (
                        <span>@{viewingToken.created_by_login} <span className="text-muted-foreground font-normal">(#{viewingToken.created_by_account_id})</span></span>
                      ) : viewingToken.created_by_account_id ? (
                        <span>Аккаунт #{viewingToken.created_by_account_id}</span>
                      ) : (
                        <span className="text-muted-foreground">Система</span>
                      )}
                    </div>
                  </div>

                  <div className="p-3 rounded-lg border border-border/60 bg-muted/10 space-y-1.5">
                    <span className="text-[11px] text-muted-foreground font-medium block">
                      Срок действия
                    </span>
                    <div className="flex items-center gap-1.5 text-foreground font-medium">
                      <Clock className="size-3.5 text-muted-foreground" />
                      {viewingToken.expires_at ? (
                        <span>До {new Date(viewingToken.expires_at).toLocaleString()}</span>
                      ) : (
                        <span className="text-emerald-500">Бессрочный</span>
                      )}
                    </div>
                  </div>

                  <div className="p-3 rounded-lg border border-border/60 bg-muted/10 space-y-1.5">
                    <span className="text-[11px] text-muted-foreground font-medium block">
                      Создан в системе
                    </span>
                    <div className="text-foreground">
                      {new Date(viewingToken.created_at).toLocaleString()}
                    </div>
                  </div>

                  <div className="p-3 rounded-lg border border-border/60 bg-muted/10 space-y-1.5 col-span-2">
                    <span className="text-[11px] text-muted-foreground font-medium block">
                      Последняя активность
                    </span>
                    <div className="text-foreground">
                      {viewingToken.last_used_at ? (
                        <div>
                          <span>{new Date(viewingToken.last_used_at).toLocaleString()}</span>
                          <span className="text-muted-foreground ml-1 font-mono text-[11px]">
                            ({viewingToken.last_used_ip || "неизвестно"})
                          </span>
                        </div>
                      ) : (
                        <span className="text-muted-foreground">Еще не использовался</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* IP Allowlist */}
                <div className="space-y-1.5 rounded-lg border border-border/60 bg-muted/10 p-3">
                  <span className="text-[11px] text-muted-foreground font-medium flex items-center gap-1.5">
                    <Globe className="size-3.5 text-muted-foreground" />
                    Ограничения по IP-адресам
                  </span>
                  {viewingToken.ip_allowlist && viewingToken.ip_allowlist.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {viewingToken.ip_allowlist.map((ip) => (
                        <Badge key={ip} variant="outline" className="font-mono text-xs">
                          {ip}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <p className="text-muted-foreground text-[11px] pt-0.5">
                      Доступ открыт с любых IP-адресов (без ограничений).
                    </p>
                  )}
                </div>

                {/* Scoped RBAC Permissions */}
                <div className="space-y-2 rounded-lg border border-border/60 bg-muted/10 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-muted-foreground font-medium flex items-center gap-1.5">
                      <Shield className="size-3.5 text-primary" />
                      Назначенные права доступа (Scoped RBAC)
                    </span>
                    <Badge variant="secondary" className="text-[10px]">
                      {viewingToken.permissions.length} прав
                    </Badge>
                  </div>

                  {viewingToken.permissions.length === 0 ? (
                    <p className="text-muted-foreground text-[11px] py-1">
                      У данного токена нет активных разрешений.
                    </p>
                  ) : (
                    <div className="flex flex-wrap gap-1.5 max-h-[180px] overflow-y-auto p-2 rounded border border-border/40 bg-background/60">
                      {viewingToken.permissions.map((p) => (
                        <Badge key={p} variant="secondary" className="font-mono text-[11px]">
                          {p}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <DialogFooter className="flex items-center justify-between gap-2 pt-2 border-t border-border/40">
                <div className="flex items-center gap-2">
                  {canManageToken(viewingToken) ? (
                    <>
                      {!viewingToken.is_revoked && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => setRevokingToken(viewingToken)}
                          className="text-xs text-amber-500 hover:text-amber-400 hover:bg-amber-500/10"
                        >
                          Отозвать токен
                        </Button>
                      )}
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setDeletingToken(viewingToken)}
                        className="text-xs text-destructive hover:bg-destructive/10"
                      >
                        <Trash2 className="size-3.5 mr-1" /> Удалить токен
                      </Button>
                    </>
                  ) : (
                    <span className="text-[11px] text-muted-foreground italic">
                      Управление этим токеном доступно только его создателю или администраторам.
                    </span>
                  )}
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setViewingToken(null)}
                  className="text-xs"
                >
                  Закрыть
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* One-Time Secret Reveal Dialog */}
      <Dialog open={revealedToken !== null} onOpenChange={() => setRevealedToken(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-primary">
              <KeyRound className="size-5" /> Токен успешно создан
            </DialogTitle>
            <DialogDescription>
              Полномочия привязаны к созданному ключу. Сохраните токен сейчас!
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3.5 flex items-start gap-3">
              <AlertTriangle className="size-5 text-amber-500 shrink-0 mt-0.5" />
              <div className="text-xs space-y-1 text-amber-200">
                <p className="font-semibold text-amber-400">
                  Секретный ключ отображается СТРОГО ОДИН РАЗ
                </p>
                <p className="text-muted-foreground leading-relaxed">
                  В целях безопасности мы храним в базе данных только необратимый криптографический хэш.
                  После закрытия этого окна восстановить или просмотреть токен будет невозможно.
                </p>
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="text-xs">Секретный ключ авторизации (Bearer Token)</Label>
                <span className="text-[10px] text-muted-foreground font-mono">
                  Идентификатор: {revealedToken?.token_prefix}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Input
                  readOnly
                  value={revealedToken?.secret_token || ""}
                  className="font-mono text-xs bg-muted/60 select-all"
                />
                <Button
                  onClick={handleCopySecret}
                  variant={copiedSecret ? "default" : "secondary"}
                  className="shrink-0 gap-1.5 text-xs"
                >
                  {copiedSecret ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                  {copiedSecret ? "Скопировано!" : "Копировать"}
                </Button>
              </div>
            </div>

            <div className="rounded-md border border-border/40 bg-muted/20 p-2.5 text-[11px] text-muted-foreground">
              <p className="font-medium text-foreground">Пример использования в заголовке запроса:</p>
              <code className="block mt-1 p-1.5 bg-background rounded text-primary font-mono text-[10px] break-all">
                Authorization: Bearer {revealedToken?.secret_token}
              </code>
            </div>
          </div>

          <DialogFooter>
            <Button onClick={() => setRevealedToken(null)} className="text-xs">
              Я сохранил токен
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Revoke confirmation */}
      <AlertDialog open={revokingToken !== null} onOpenChange={() => setRevokingToken(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Отозвать токен «{revokingToken?.name}»?</AlertDialogTitle>
            <AlertDialogDescription>
              Все внешние сервисы, боты или скрипты, использующие ключ с префиксом «{revokingToken?.token_prefix}»,
              мгновенно потеряют доступ к API платформы. Это действие необратимо.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => revokingToken && revokeMutation.mutate(revokingToken.id)}
              className="bg-amber-600 hover:bg-amber-700 text-white"
            >
              Отозвать токен
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete confirmation */}
      <AlertDialog open={deletingToken !== null} onOpenChange={() => setDeletingToken(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить токен «{deletingToken?.name}»?</AlertDialogTitle>
            <AlertDialogDescription>
              Токен будет безвозвратно удален из системы вместе с историей активности.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deletingToken && deleteMutation.mutate(deletingToken.id)}
              className="bg-destructive hover:bg-destructive/90 text-white"
            >
              Удалить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
