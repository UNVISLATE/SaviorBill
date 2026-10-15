import { useState, useRef, type ChangeEvent, type DragEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  Camera,
  Copy,
  KeyRound,
  Trash2,
  Wallet,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { toastError, toastSuccess } from "@/lib/toast.ts"
import { useAuth } from "@/hooks/use-auth.tsx"
import { useProfileDialog } from "@/hooks/use-profile-dialog"
import {
  useUserProfile,
  useInvalidateUserProfile,
  type UserProfile,
} from "@/hooks/use-user-profile.ts"
import { uploadOwnMedia } from "@/api/media-upload.ts"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/shadsnui/avatar"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Field, FieldLabel } from "@/components/shadsnui/field"
import { Input } from "@/components/shadsnui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import { Progress } from "@/components/shadsnui/progress"
import { Separator } from "@/components/shadsnui/separator"
import { Skeleton } from "@/components/shadsnui/skeleton"

interface Role {
  id: number
  key: string
  name: string
}

interface OAuthProvider {
  slug: string
  title: string
  icon_url: string | null
}

interface UserOAuthConn {
  id: number
  provider: string
  subject: string
  email?: string | null
  created_at?: string
}

const KNOWN_PROVIDERS: Record<string, { title: string; icon: string }> = {
  google: { title: "Google", icon: "🌐" },
  telegram: { title: "Telegram", icon: "✈️" },
  discord: { title: "Discord", icon: "💬" },
  vk: { title: "ВКонтакте", icon: "🔵" },
  github: { title: "GitHub", icon: "🐙" },
  yandex: { title: "Яндекс", icon: "🔴" },
}

function initials(login: string): string {
  return login.slice(0, 2).toUpperCase()
}

/** Диалог пополнения/списания баланса (обычного или бонусного) — использует
 * POST /admin/users/{id}/balance (дельта + причина для аудита). */
function BalanceAdjustDialog({
  userId,
  kind,
  open,
  onOpenChange,
}: {
  userId: number
  kind: "main" | "bonus"
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [amount, setAmount] = useState("")
  const [reason, setReason] = useState("")
  const qc = useQueryClient()

  const adjust = useMutation({
    mutationFn: async () => {
      const num = Number(amount)
      if (Number.isNaN(num) || num === 0) throw new Error("Укажите сумму (не ноль)")
      await api.post(`/v1/admin/users/${userId}/balance`, {
        delta: num.toString(),
        is_bonus: kind === "bonus",
        reason: reason.trim(),
      })
    },
    onSuccess: () => {
      const num = Number(amount)
      const actionText = num > 0 ? "Начислено" : "Списано"
      toastSuccess(
        `${actionText} ${Math.abs(num)} ₽ на ${kind === "bonus" ? "бонусный" : "основной"} баланс`,
      )
      onOpenChange(false)
      setAmount("")
      setReason("")
      qc.invalidateQueries({ queryKey: ["admin-user-profile", userId] })
      qc.invalidateQueries({ queryKey: ["admin-users"] })
    },
    onError: (e: unknown) => {
      toastError("Ошибка изменения баланса", getErrorDetail(e))
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>
            {kind === "bonus" ? "Бонусный баланс" : "Основной баланс"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Field>
            <FieldLabel htmlFor="balance-delta-amount">Сумма (₽)</FieldLabel>
            <Input
              id="balance-delta-amount"
              type="number"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="+100.00 или -50.00"
              autoFocus
            />
            <p className="text-[11px] text-muted-foreground">
              Положительное число — начислить, отрицательное со знаком минус — списать.
            </p>
          </Field>
          <Field>
            <FieldLabel htmlFor="balance-delta-reason">Причина (для аудита)</FieldLabel>
            <Input
              id="balance-delta-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="ручная корректировка"
            />
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            disabled={!amount || Number(amount) === 0 || Number.isNaN(Number(amount)) || !reason.trim() || adjust.isPending}
            onClick={() => adjust.mutate()}
          >
            Применить
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ProfileOverviewSection({
  mode,
  userId,
  onDeleteClick,
}: {
  mode: "own" | "view"
  userId?: number
  onDeleteClick?: () => void
}) {
  const isOwn = mode === "own"
  const qc = useQueryClient()
  const { can } = useAuth()
  const ownProfile = useUserProfile()
  const invalidateOwnProfile = useInvalidateUserProfile()
  const viewProfile = useQuery({
    queryKey: ["admin-user-profile", userId],
    queryFn: async () => (await api.get<UserProfile>(`/v1/admin/users/${userId}/profile`)).data,
    enabled: !isOwn,
  })
  const { data: profile, isLoading } = isOwn ? ownProfile : viewProfile
  const invalidateProfile = () => {
    if (isOwn) {
      invalidateOwnProfile()
    } else {
      qc.invalidateQueries({ queryKey: ["admin-user-profile", userId] })
      qc.invalidateQueries({ queryKey: ["admin-user-brief", userId] })
    }
  }
  const canEditEmail = isOwn || can("admin.user.edit")
  const canManageAvatar = isOwn || can("admin.media.manage_any")
  const canEditRole = !isOwn && can("admin.user.role.edit")
  const canAdjustBalance = !isOwn && can("admin.user.balance.edit")
  const canDelete = can("admin.user.delete")
  const isOwnerTarget = !isOwn && profile?.role === "owner"

  const { data: roles } = useQuery({
    queryKey: ["admin-roles-lookup"],
    queryFn: async () => (await api.get<Role[]>("/v1/admin/roles")).data,
    staleTime: 5 * 60_000,
    enabled: canEditRole,
  })
  const assignableRoles = roles?.filter((r) => r.key !== "owner") ?? []

  const { setBusy } = useProfileDialog()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [uploadPct, setUploadPct] = useState<number | null>(null)
  const [dragOver, setDragOver] = useState(false)

  const [login, setLogin] = useState("")
  const [email, setEmail] = useState("")
  const [savingProfile, setSavingProfile] = useState(false)

  const [pwOpen, setPwOpen] = useState(false)
  const [pwCurrent, setPwCurrent] = useState("")
  const [pwNew, setPwNew] = useState("")
  const [pwSaving, setPwSaving] = useState(false)

  const [idCopied, setIdCopied] = useState(false)
  const [topUpKind, setTopUpKind] = useState<"main" | "bonus" | null>(null)

  const [syncedFor, setSyncedFor] = useState<number | null>(null)
  if (profile && syncedFor !== profile.id) {
    setLogin(profile.login)
    setEmail(profile.email ?? "")
    setSyncedFor(profile.id)
  }

  async function doUpload(file: File) {
    if (!isOwn && !canManageAvatar) return
    setUploadPct(0)
    setBusy(true)
    try {
      const { mediaId } = await uploadOwnMedia(file, {
        tag: "avatar",
        onProgress: (p: { loaded: number; total: number }) => setUploadPct(Math.round((p.loaded / Math.max(p.total, 1)) * 100)),
      })
      if (isOwn) {
        await api.put("/v1/user/me/avatar", { media_id: mediaId })
      } else if (userId) {
        await api.put(`/v1/admin/users/${userId}/avatar`, { media_id: mediaId })
      }
      invalidateProfile()
      toastSuccess("Аватар обновлён")
    } catch (err) {
      toastError("Не удалось загрузить аватар", err instanceof Error ? err.message : undefined)
    } finally {
      setUploadPct(null)
      setBusy(false)
    }
  }

  const { data: oauthProviders } = useQuery({
    queryKey: ["oauth-providers"],
    queryFn: async () => (await api.get<OAuthProvider[]>("/v1/oauth/providers")).data,
    staleTime: 60_000,
  })

  const { data: userOauthConns, refetch: refetchConns } = useQuery({
    queryKey: isOwn ? ["user-oauth"] : ["admin-user-oauth", userId],
    queryFn: async () => {
      const url = isOwn ? "/v1/user/oauth" : `/v1/admin/users/${userId}/oauth`
      return (await api.get<UserOAuthConn[]>(url)).data
    },
    enabled: isOwn || !!userId,
  })

  const linkOAuth = async (providerSlug: string) => {
    try {
      const res = await api.get<{ authorize_url: string }>(`/v1/user/oauth/${providerSlug}/link`)
      if (res.data.authorize_url) {
        window.location.assign(res.data.authorize_url)
      }
    } catch (err) {
      toastError("Не удалось инициировать привязку", getErrorDetail(err))
    }
  }

  const unlinkOAuth = useMutation({
    mutationFn: async (providerSlug: string) => {
      if (isOwn) {
        await api.delete(`/v1/user/oauth/${providerSlug}`)
      } else if (userId) {
        await api.delete(`/v1/admin/users/${userId}/oauth/${providerSlug}`)
      }
    },
    onSuccess: () => {
      toastSuccess("Привязка удалена")
      void refetchConns()
      invalidateProfile()
    },
    onError: (err) => {
      toastError("Не удалось отвязать аккаунт", getErrorDetail(err))
    },
  })

  const displayProviders = [
    ...(oauthProviders ?? []),
    ...(userOauthConns ?? [])
      .filter((c) => !oauthProviders?.some((p) => p.slug === c.provider))
      .map((c) => ({
        slug: c.provider,
        title: KNOWN_PROVIDERS[c.provider]?.title ?? c.provider,
        icon_url: null,
      })),
  ]

  async function clearAvatar() {
    if (!userId && !isOwn) return
    setBusy(true)
    try {
      if (isOwn) {
        await api.put("/v1/user/me/avatar", { media_id: null })
      } else {
        await api.put(`/v1/admin/users/${userId}/avatar`, { media_id: null })
      }
      invalidateProfile()
      toastSuccess("Аватар сброшен")
    } catch {
      toastError("Не удалось сбросить аватар")
    } finally {
      setBusy(false)
    }
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (file) void doUpload(file)
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) void doUpload(file)
  }

  async function handleSaveProfile() {
    if (!profile) return
    setSavingProfile(true)
    try {
      if (isOwn) {
        const patch: Record<string, string> = {}
        if (login !== profile.login) patch.login = login
        if (email !== (profile.email ?? "")) patch.email = email
        if (Object.keys(patch).length > 0) {
          await api.patch("/v1/user/me", patch)
          invalidateProfile()
        }
      } else if (canEditEmail && email !== (profile.email ?? "")) {
        await api.patch(`/v1/admin/users/${userId}`, { email })
        invalidateProfile()
      }
      toastSuccess("Профиль сохранён")
    } catch {
      toastError("Не удалось сохранить", "логин/email могут быть уже заняты")
    } finally {
      setSavingProfile(false)
    }
  }

  async function handleRoleChange(roleId: string) {
    if (!userId) return
    try {
      await api.patch(`/v1/admin/users/${userId}`, { role_id: Number(roleId) })
      invalidateProfile()
      toastSuccess("Роль изменена")
    } catch (e: unknown) {
      toastError("Не удалось изменить роль", getErrorDetail(e))
    }
  }

  async function handleChangePassword() {
    setPwSaving(true)
    try {
      await api.post("/v1/user/me/password", {
        current_password: pwCurrent || undefined,
        new_password: pwNew,
      })
      toastSuccess("Пароль изменён")
      setPwOpen(false)
      setPwCurrent("")
      setPwNew("")
    } catch {
      toastError("Не удалось сменить пароль", "проверьте текущий пароль")
    } finally {
      setPwSaving(false)
    }
  }

  const toggleActive = useMutation({
    mutationFn: async () => {
      if (!userId || !profile) return
      await api.patch(`/v1/admin/users/${userId}`, { is_active: !profile.is_active })
    },
    onSuccess: () => {
      invalidateProfile()
      toastSuccess(profile?.is_active ? "Аккаунт заблокирован" : "Аккаунт разблокирован")
    },
    onError: (e) => toastError("Не удалось изменить статус", getErrorDetail(e)),
  })

  const revokeSessions = useMutation({
    mutationFn: async () => {
      if (isOwn) {
        await api.delete("/v1/user/me/sessions")
      } else if (userId) {
        await api.delete(`/v1/admin/users/${userId}/sessions`)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: isOwn ? ["user-sessions"] : ["admin-user-sessions", userId] })
      toastSuccess("Все активные сессии завершены")
    },
    onError: (e) => toastError("Не удалось завершить сессии", getErrorDetail(e)),
  })

  async function copyId() {
    if (!profile) return
    await navigator.clipboard.writeText(String(profile.id))
    setIdCopied(true)
    setTimeout(() => setIdCopied(false), 1500)
  }

  const profileDirty =
    !!profile &&
    ((isOwn && (login !== profile.login || email !== (profile.email ?? ""))) ||
      (!isOwn && canEditEmail && email !== (profile.email ?? "")))

  if (isLoading || !profile) {
    return (
      <div className="space-y-4">
        <Skeleton className="size-20 rounded-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </div>
    )
  }

  const currentRoleObj = roles?.find((r) => r.name === profile.role)

  return (
    <div className="space-y-6">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Верхняя плашка: Аватар + Никнейм, ID, Роль + Баланс */}
      <div className="flex items-center gap-4">
        <div
          className={`group relative size-16 shrink-0 rounded-full transition-all ${
            (isOwn || canManageAvatar) ? "cursor-pointer" : ""
          } ${dragOver ? "ring-2 ring-primary" : ""}`}
          onDragOver={(e) => {
            if (!isOwn && !canManageAvatar) return
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => {
            if ((isOwn || canManageAvatar) && uploadPct === null) fileInputRef.current?.click()
          }}
          title={isOwn || canManageAvatar ? "Нажмите для выбора файла или перетащите изображение" : undefined}
        >
          <Avatar className="size-16 ring-2 ring-border/50 transition group-hover:ring-primary">
            {profile.avatar_url && <AvatarImage src={profile.avatar_url} alt={profile.login} />}
            <AvatarFallback className="bg-muted text-lg font-semibold">
              {initials(profile.login)}
            </AvatarFallback>
          </Avatar>

          {(isOwn || canManageAvatar) && (
            <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40 opacity-0 transition-opacity group-hover:opacity-100">
              <Camera className="size-5 text-white" />
            </div>
          )}

          {canManageAvatar && profile.avatar_url && (
            <Button
              type="button"
              size="icon-xs"
              variant="destructive"
              className="absolute -bottom-1 -right-1 size-5 rounded-full shadow-sm"
              title="Удалить аватар"
              onClick={(e) => {
                e.stopPropagation()
                void clearAvatar()
              }}
            >
              <Trash2 className="size-3" />
            </Button>
          )}
        </div>

        <div className="min-w-0 flex-1 space-y-2">
          {/* Строка 1: Логин + ID + Роль + Статус */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-bold text-foreground tracking-tight sm:text-lg">
              {profile.login}
            </span>

            <button
              type="button"
              onClick={copyId}
              className="flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 font-mono text-xs text-muted-foreground transition hover:text-foreground"
              title="Скопировать ID"
            >
              ID: {profile.id}
              <Copy className="size-3" />
              {idCopied && <span className="text-[10px] text-emerald-500">скопировано</span>}
            </button>

            {canEditRole ? (
              <Select
                value={currentRoleObj?.id.toString() ?? ""}
                onValueChange={(v) => v && handleRoleChange(v)}
              >
                <SelectTrigger size="sm" className="h-7 w-auto min-w-[120px] px-2 text-xs">
                  <SelectValue placeholder={profile.role ?? "—"}>
                    {currentRoleObj?.name ?? profile.role ?? "—"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {assignableRoles.map((r) => (
                    <SelectItem key={r.id} value={String(r.id)}>
                      {r.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              profile.role && (
                <Badge variant={profile.role === "owner" ? "default" : "secondary"}>
                  {profile.role}
                  {isOwnerTarget && " — неприкасаема"}
                </Badge>
              )
            )}

            {!profile.is_active && (
              <Badge variant="destructive">заблокирован</Badge>
            )}
          </div>

          {/* Строка 2: Баланс + Бонусный баланс плашками (клик = открытие) */}
          <div className="flex flex-wrap items-center gap-2">
            <div
              role={canAdjustBalance && !isOwnerTarget ? "button" : undefined}
              tabIndex={canAdjustBalance && !isOwnerTarget ? 0 : undefined}
              onClick={() => {
                if (canAdjustBalance && !isOwnerTarget) setTopUpKind("main")
              }}
              title={canAdjustBalance && !isOwnerTarget ? "Нажмите для изменения баланса" : undefined}
              className={`flex items-center gap-1.5 rounded-md border bg-muted/40 px-2.5 py-1 text-xs select-none transition-colors ${
                canAdjustBalance && !isOwnerTarget
                  ? "cursor-pointer hover:bg-muted/80 hover:border-foreground/30 active:scale-95"
                  : ""
              }`}
            >
              <Wallet className="size-3.5 text-muted-foreground" />
              <span className="text-muted-foreground">Баланс:</span>
              <span className="font-semibold tabular-nums text-foreground">{profile.balance} ₽</span>
            </div>

            <div
              role={canAdjustBalance && !isOwnerTarget ? "button" : undefined}
              tabIndex={canAdjustBalance && !isOwnerTarget ? 0 : undefined}
              onClick={() => {
                if (canAdjustBalance && !isOwnerTarget) setTopUpKind("bonus")
              }}
              title={canAdjustBalance && !isOwnerTarget ? "Нажмите для изменения бонусного баланса" : undefined}
              className={`flex items-center gap-1.5 rounded-md border bg-muted/40 px-2.5 py-1 text-xs select-none transition-colors ${
                canAdjustBalance && !isOwnerTarget
                  ? "cursor-pointer hover:bg-muted/80 hover:border-foreground/30 active:scale-95"
                  : ""
              }`}
            >
              <span className="text-muted-foreground">Бонусный:</span>
              <span className="font-semibold tabular-nums text-foreground">{profile.bonus_balance} ₽</span>
            </div>
          </div>

          {uploadPct !== null && (
            <div className="w-56 space-y-1 pt-1">
              <Progress value={uploadPct} />
            </div>
          )}
        </div>
      </div>

      <Separator />

      {/* Учётные данные: 2 колонки (Логин + Email) + Смена пароля */}
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium">Учётные данные</p>
          {profileDirty && (
            <Button type="button" size="sm" onClick={handleSaveProfile} disabled={savingProfile}>
              {savingProfile ? "Сохранение…" : "Сохранить"}
            </Button>
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="profile-login">Логин</FieldLabel>
            <Input
              id="profile-login"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              readOnly={!isOwn}
              disabled={!isOwn}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="profile-email">Email</FieldLabel>
            <Input
              id="profile-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              readOnly={!canEditEmail}
              disabled={!canEditEmail}
            />
          </Field>
        </div>

        {isOwn && (!pwOpen ? (
          <Button type="button" size="sm" variant="outline" onClick={() => setPwOpen(true)}>
            <KeyRound className="mr-1.5 size-3.5" />
            Изменить пароль
          </Button>
        ) : (
          <div className="space-y-3 rounded-md border p-3">
            <Field>
              <FieldLabel htmlFor="profile-pw-current">Текущий пароль</FieldLabel>
              <Input
                id="profile-pw-current"
                type="password"
                value={pwCurrent}
                onChange={(e) => setPwCurrent(e.target.value)}
                placeholder="оставьте пустым, если пароля ещё нет (OAuth)"
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="profile-pw-new">Новый пароль</FieldLabel>
              <Input
                id="profile-pw-new"
                type="password"
                value={pwNew}
                onChange={(e) => setPwNew(e.target.value)}
              />
            </Field>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                onClick={handleChangePassword}
                disabled={pwSaving || pwNew.length < 8}
              >
                {pwSaving ? "Сохранение…" : "Сохранить пароль"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setPwOpen(false)
                  setPwCurrent("")
                  setPwNew("")
                }}
              >
                Отмена
              </Button>
            </div>
          </div>
        ))}
      </div>

      {displayProviders.length > 0 && (
        <>
          <Separator />

          {/* OAuth / Связанные аккаунты */}
          <div className="space-y-3">
            <div>
              <h4 className="text-sm font-medium">Связанные аккаунты</h4>
              <p className="text-xs text-muted-foreground">
                Вход через сторонние сервисы и привязанные провайдеры.
              </p>
            </div>

            <div className="divide-y divide-border rounded-lg border bg-card">
              {displayProviders.map((provider) => {
                const conn = userOauthConns?.find((c) => c.provider === provider.slug)
                const isConnected = !!conn
                return (
                  <div key={provider.slug} className="flex items-center justify-between p-3">
                    <div className="flex items-center gap-3">
                      {provider.icon_url ? (
                        <img
                          src={provider.icon_url}
                          alt={provider.title}
                          className="size-6 rounded object-contain"
                        />
                      ) : (
                        <div className="flex size-6 items-center justify-center rounded bg-muted text-xs font-semibold">
                          {KNOWN_PROVIDERS[provider.slug]?.icon ?? provider.title.charAt(0)}
                        </div>
                      )}
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">{provider.title}</span>
                          {isConnected ? (
                            <Badge
                              variant="outline"
                              className="border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0 text-[10px] text-emerald-600 dark:text-emerald-400"
                            >
                              Подключён
                            </Badge>
                          ) : (
                            <span className="text-[11px] text-muted-foreground">Не подключён</span>
                          )}
                        </div>
                        {conn?.email && (
                          <p className="text-xs text-muted-foreground">{conn.email}</p>
                        )}
                      </div>
                    </div>

                    <div>
                      {isConnected ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="h-8 px-2.5 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive"
                          disabled={unlinkOAuth.isPending}
                          onClick={() => unlinkOAuth.mutate(provider.slug)}
                        >
                          Отвязать
                        </Button>
                      ) : isOwn ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="h-8 px-2.5 text-xs"
                          onClick={() => linkOAuth(provider.slug)}
                        >
                          Подключить
                        </Button>
                      ) : null}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </>
      )}

      <Separator />

      {/* Danger Zone (GitHub-style) */}
      <div className="space-y-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4">
        <div className="flex items-center gap-2">
          <AlertTriangle className="size-4 text-destructive" />
          <h4 className="text-sm font-semibold text-destructive">Danger Zone</h4>
        </div>

        <div className="divide-y divide-destructive/20 text-xs">
          {/* Блокировка/разблокировка чужого аккаунта */}
          {!isOwn && (
            <div className="flex items-center justify-between py-2.5">
              <div className="space-y-0.5 pr-4">
                <p className="font-medium text-foreground">
                  {profile.is_active ? "Заблокировать аккаунт" : "Разблокировать аккаунт"}
                </p>
                <p className="text-muted-foreground">
                  {profile.is_active
                    ? "Пользователь потеряет доступ к сервису и API."
                    : "Восстановить доступ пользователя к сервису."}
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className={
                  profile.is_active
                    ? "border-destructive/30 text-destructive hover:bg-destructive/10"
                    : "border-emerald-500/30 text-emerald-600 hover:bg-emerald-500/10"
                }
                disabled={isOwnerTarget || toggleActive.isPending}
                onClick={() => toggleActive.mutate()}
              >
                {profile.is_active ? "Заблокировать" : "Разблокировать"}
              </Button>
            </div>
          )}

          {/* Сброс активных сессий */}
          <div className="flex items-center justify-between py-2.5">
            <div className="space-y-0.5 pr-4">
              <p className="font-medium text-foreground">Сбросить активные сессии</p>
              <p className="text-muted-foreground">
                {isOwn
                  ? "Завершить сессии на всех остальных устройствах."
                  : "Принудительно отозвать все выданные токены и завершить сессии."}
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="border-destructive/30 text-destructive hover:bg-destructive/10"
              disabled={revokeSessions.isPending}
              onClick={() => revokeSessions.mutate()}
            >
              Завершить сессии
            </Button>
          </div>

          {/* Удаление пользователя */}
          {!isOwn && canDelete && !isOwnerTarget && (
            <div className="flex items-center justify-between py-2.5">
              <div className="space-y-0.5 pr-4">
                <p className="font-medium text-destructive">Удалить пользователя</p>
                <p className="text-muted-foreground">
                  Полное и безвозвратное удаление аккаунта, заказов и платежей.
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="destructive"
                onClick={onDeleteClick}
              >
                Удалить пользователя
              </Button>
            </div>
          )}
        </div>
      </div>

      {topUpKind && userId && (
        <BalanceAdjustDialog
          userId={userId}
          kind={topUpKind}
          open={!!topUpKind}
          onOpenChange={(v) => !v && setTopUpKind(null)}
        />
      )}
    </div>
  )
}
