import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  Bot,
  Calendar,
  Check,
  Copy,
  Globe,
  KeyRound,
  Plus,
  Search,
  Shield,
  Trash2,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { Badge } from "@/components/shadsnui/badge"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Textarea } from "@/components/shadsnui/textarea"
import { Checkbox } from "@/components/shadsnui/checkbox"
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

interface AppToken {
  id: number
  name: string
  description: string | null
  token_prefix: string
  permissions: string[]
  ip_allowlist: string[] | null
  created_by_account_id: number | null
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

interface PermsCatalog {
  flat: string[]
  tree: Record<string, unknown>
}

export function AppTokensSettings() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [revealedToken, setRevealedToken] = useState<AppTokenCreated | null>(null)
  const [copied, setCopied] = useState(false)

  // Creation form state
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [ipAllowlistRaw, setIpAllowlistRaw] = useState("")
  const [expiryDays, setExpiryDays] = useState<number | "never">("never")
  const [selectedPerms, setSelectedPerms] = useState<Set<string>>(new Set())
  const [permSearch, setPermSearch] = useState("")

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

  const createMutation = useMutation({
    mutationFn: async () => {
      let expires_at: string | null = null
      if (expiryDays !== "never") {
        const d = new Date()
        d.setDate(d.getDate() + expiryDays)
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
      toastError(err?.response?.data?.detail || "Не удалось создать токен")
    },
  })

  const revokeMutation = useMutation({
    mutationFn: async (id: number) => {
      await api.post(`/v1/admin/app-tokens/${id}/revoke`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-app-tokens"] })
      setRevokingToken(null)
      toastSuccess("Токен отозван")
    },
    onError: () => toastError("Не удалось отозвать токен"),
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/v1/admin/app-tokens/${id}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-app-tokens"] })
      setDeletingToken(null)
      toastSuccess("Токен удален")
    },
    onError: () => toastError("Не удалось удалить токен"),
  })

  const resetForm = () => {
    setName("")
    setDescription("")
    setIpAllowlistRaw("")
    setExpiryDays("never")
    setSelectedPerms(new Set())
    setPermSearch("")
  }

  const handleCopy = () => {
    if (!revealedToken) return
    navigator.clipboard.writeText(revealedToken.secret_token)
    setCopied(true)
    toastSuccess("Секретный токен скопирован в буфер обмена")
    setTimeout(() => setCopied(false), 3000)
  }

  const togglePerm = (perm: string) => {
    const next = new Set(selectedPerms)
    if (next.has(perm)) {
      next.delete(perm)
    } else {
      next.add(perm)
    }
    setSelectedPerms(next)
  }

  const toggleAllCategory = (allInCat: string[]) => {
    const next = new Set(selectedPerms)
    const allSelected = allInCat.every((p) => next.has(p))
    if (allSelected) {
      allInCat.forEach((p) => next.delete(p))
    } else {
      allInCat.forEach((p) => next.add(p))
    }
    setSelectedPerms(next)
  }

  // Filtered perms
  const allPermsList = useMemo(() => permsCatalog?.flat || [], [permsCatalog])

  const categorizedPerms = useMemo(() => {
    const groups: Record<string, string[]> = {}
    for (const p of allPermsList) {
      if (permSearch.trim() && !p.toLowerCase().includes(permSearch.toLowerCase())) {
        continue
      }
      const cat = p.split(".")[0] || "other"
      if (!groups[cat]) groups[cat] = []
      groups[cat].push(p)
    }
    return groups
  }, [allPermsList, permSearch])

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

          <div className="space-y-1.5">
            <Label className="text-xs flex items-center gap-1.5">
              <Calendar className="size-3.5 text-muted-foreground" /> Срок действия
            </Label>
            <div className="grid grid-cols-4 gap-2">
              {[
                { label: "Бессрочно", val: "never" as const },
                { label: "30 дней", val: 30 },
                { label: "90 дней", val: 90 },
                { label: "1 год", val: 365 },
              ].map((opt) => (
                <Button
                  key={String(opt.val)}
                  type="button"
                  variant={expiryDays === opt.val ? "default" : "outline"}
                  size="sm"
                  onClick={() => setExpiryDays(opt.val)}
                  className="text-xs h-8"
                >
                  {opt.label}
                </Button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs flex items-center gap-1.5">
              <Globe className="size-3.5 text-muted-foreground" /> Белый список IP / CIDR (опционально)
            </Label>
            <Textarea
              value={ipAllowlistRaw}
              onChange={(e) => setIpAllowlistRaw(e.target.value)}
              placeholder="192.168.1.10&#10;10.0.0.0/24&#10;(по одному на строку или через запятую; пусто = любые IP)"
              rows={3}
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
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
              <Input
                value={permSearch}
                onChange={(e) => setPermSearch(e.target.value)}
                placeholder="Поиск по правам (например: orders, apptokens, services)..."
                className="pl-8 h-8 text-xs"
              />
            </div>
            {selectedPerms.size > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedPerms(new Set())}
                className="text-xs h-8"
              >
                Снять все ({selectedPerms.size})
              </Button>
            )}
          </div>

          <div className="max-h-[340px] overflow-y-auto rounded-lg border border-border/60 p-2.5 space-y-4 bg-background/50">
            {Object.keys(categorizedPerms).length === 0 ? (
              <div className="py-6 text-center text-xs text-muted-foreground">
                Права не найдены
              </div>
            ) : (
              Object.entries(categorizedPerms).map(([cat, perms]) => {
                const allChecked = perms.every((p) => selectedPerms.has(p))
                return (
                  <div key={cat} className="space-y-1.5">
                    <div className="flex items-center justify-between pb-1 border-b border-border/40">
                      <span className="text-xs font-semibold capitalize tracking-wide text-foreground/90">
                        {cat} ({perms.length})
                      </span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => toggleAllCategory(perms)}
                        className="text-[10px] h-6 px-1.5 text-muted-foreground hover:text-foreground"
                      >
                        {allChecked ? "Снять все" : "Выбрать все"}
                      </Button>
                    </div>
                    <div className="grid grid-cols-2 gap-1.5">
                      {perms.map((p) => (
                        <label
                          key={p}
                          className="flex items-center gap-2 rounded px-2 py-1.5 text-xs hover:bg-muted/50 cursor-pointer border border-transparent hover:border-border/40 transition-colors"
                        >
                          <Checkbox
                            checked={selectedPerms.has(p)}
                            onCheckedChange={() => togglePerm(p)}
                          />
                          <span className="font-mono text-[11px] truncate" title={p}>
                            {p}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                )
              })
            )}
          </div>
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
              <TableHead className="w-[200px]">Приложение / Название</TableHead>
              <TableHead>Маска токена</TableHead>
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
                <TableCell colSpan={7} className="text-center py-8 text-xs text-muted-foreground">
                  Загрузка токенов...
                </TableCell>
              </TableRow>
            ) : tokens.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-12 text-muted-foreground">
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
                return (
                  <TableRow key={token.id} className={token.is_revoked ? "opacity-60 bg-muted/20" : ""}>
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
                      <Badge variant="outline" className="font-mono text-[11px]">
                        {token.token_prefix}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1 max-w-[240px]">
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
                      <div className="flex items-center justify-end gap-1">
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
              <Label className="text-xs">Секретный ключ авторизации (Bearer Token)</Label>
              <div className="flex items-center gap-2">
                <Input
                  readOnly
                  value={revealedToken?.secret_token || ""}
                  className="font-mono text-xs bg-muted/60 select-all"
                />
                <Button
                  onClick={handleCopy}
                  variant={copied ? "default" : "secondary"}
                  className="shrink-0 gap-1.5 text-xs"
                >
                  {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                  {copied ? "Скопировано!" : "Копировать"}
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
              Все внешние сервисы, боты или скрипты, использующие этот ключ, мгновенно потеряют доступ
              к API платформы. Это действие необратимо.
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
