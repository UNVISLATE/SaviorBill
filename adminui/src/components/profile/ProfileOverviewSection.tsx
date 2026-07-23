import { useRef, useState, type ChangeEvent, type DragEvent } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Camera, Copy, KeyRound, Loader2, MoreVertical, Users2, Wallet } from "lucide-react"

import { useProfileDialog } from "@/hooks/use-profile-dialog"
import { useInvalidateUserProfile, useUserProfile, type UserProfile } from "@/hooks/use-user-profile"
import { useAuth } from "@/hooks/use-auth"
import { api } from "@/api/api.ts"
import { uploadOwnMedia } from "@/api/media-upload.ts"
import { toastError, toastSuccess } from "@/lib/toast"
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/shadsnui/dropdown-menu"
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

function initials(login: string): string {
  return login.slice(0, 2).toUpperCase()
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  })
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
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const [amount, setAmount] = useState("")
  const [reason, setReason] = useState("")

  const adjust = useMutation({
    mutationFn: async () =>
      api.post(`/v1/admin/users/${userId}/balance`, { amount, kind, reason }),
    onSuccess: () => {
      toastSuccess(kind === "main" ? "Баланс обновлён" : "Бонусный баланс обновлён")
      onOpenChange(false)
      setAmount("")
      setReason("")
      void qc.invalidateQueries({ queryKey: ["admin-user-profile", userId] })
    },
    onError: (e: unknown) => {
      const detail =
        e && typeof e === "object" && "response" in e
          ? // @ts-expect-error — axios error shape
            e.response?.data?.detail
          : undefined
      toastError("Не удалось изменить баланс", typeof detail === "string" ? detail : undefined)
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {kind === "main" ? "Изменить баланс" : "Изменить бонусный баланс"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Field>
            <FieldLabel>Сумма (можно отрицательную — списание)</FieldLabel>
            <Input
              type="number"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="например, 500 или -100"
              autoFocus
            />
          </Field>
          <Field>
            <FieldLabel>Причина (для аудита)</FieldLabel>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="например, компенсация за инцидент"
            />
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            disabled={!amount || !reason.trim() || adjust.isPending}
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
}: {
  mode: "own" | "view"
  userId?: number
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
  const isOwnerTarget = !isOwn && profile?.role === "owner"

  const { data: roles } = useQuery({
    queryKey: ["admin-roles-lookup"],
    queryFn: async () => (await api.get<Role[]>("/v1/admin/roles")).data,
    staleTime: 5 * 60_000,
    enabled: canEditRole,
  })
  const assignableRoles = roles?.filter((r) => r.key !== "owner") ?? []

  const { me } = useAuth()
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

  // Синхронизируем локальные поля формы, когда профиль подгрузился впервые
  // (не на каждый рендер — иначе затирали бы то, что юзер уже вводит).
  // Ключ синхронизации включает id — при переключении на другой чужой
  // профиль (view-режим) форма должна пересинхронизироваться.
  const [syncedFor, setSyncedFor] = useState<number | null>(null)
  if (profile && syncedFor !== profile.id) {
    setLogin(profile.login)
    setEmail(profile.email ?? "")
    setSyncedFor(profile.id)
  }

  async function doUpload(file: File) {
    if (!isOwn) return
    setUploadPct(0)
    setBusy(true)
    try {
      const { mediaId } = await uploadOwnMedia(file, {
        tag: "avatar",
        onProgress: (p) => setUploadPct(Math.round((p.loaded / Math.max(p.total, 1)) * 100)),
      })
      await api.put("/v1/user/me/avatar", { media_id: mediaId })
      invalidateProfile()
      toastSuccess("Аватар обновлён")
    } catch (err) {
      toastError("Не удалось загрузить аватар", err instanceof Error ? err.message : undefined)
    } finally {
      setUploadPct(null)
      setBusy(false)
    }
  }

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
      const detail =
        e && typeof e === "object" && "response" in e
          ? // @ts-expect-error — axios error shape
            e.response?.data?.detail
          : undefined
      toastError("Не удалось изменить роль", typeof detail === "string" ? detail : undefined)
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

  const referralLink = profile?.ref_code
    ? `${window.location.origin}/r/${profile.ref_code}`
    : null

  async function copyReferralLink() {
    if (!referralLink) return
    await navigator.clipboard.writeText(referralLink)
    toastSuccess("Ссылка скопирована")
  }

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

  const avatarMenu = (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button type="button" className="absolute -right-1 -bottom-1 z-10">
            <span className="flex size-6 items-center justify-center rounded-full bg-popover text-muted-foreground shadow ring-1 ring-foreground/10 hover:text-foreground">
              <MoreVertical className="size-3.5" />
            </span>
          </button>
        }
      />
      <DropdownMenuContent align="start">
        {isOwn && (
          <DropdownMenuItem onClick={() => fileInputRef.current?.click()}>
            <Camera className="size-4" /> Загрузить фото
          </DropdownMenuItem>
        )}
        {canManageAvatar && profile.avatar_url && (
          <DropdownMenuItem variant="destructive" onClick={clearAvatar}>
            Сбросить аватар
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <div
          className={
            "group relative shrink-0" + (isOwn ? " cursor-pointer" : "")
          }
          onClick={() => isOwn && uploadPct === null && fileInputRef.current?.click()}
          onDragOver={(e) => {
            if (!isOwn) return
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => isOwn && setDragOver(false)}
          onDrop={isOwn ? handleDrop : undefined}
        >
          <Avatar
            className={
              "size-20 ring-2 ring-offset-2 ring-offset-background transition-all " +
              (dragOver ? "ring-primary" : "ring-transparent group-hover:ring-border")
            }
          >
            {profile.avatar_url && <AvatarImage src={profile.avatar_url} alt="" />}
            <AvatarFallback className="text-lg">
              {initials(isOwn ? me?.login ?? profile.login : profile.login)}
            </AvatarFallback>
          </Avatar>
          {isOwn && (
            <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/0 text-transparent transition-colors group-hover:bg-black/40 group-hover:text-white">
              <Camera className="size-5" />
            </div>
          )}
          {uploadPct !== null && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 rounded-full bg-background/85">
              <Loader2 className="size-5 animate-spin text-primary" />
              <span className="text-[10px] font-medium tabular-nums text-muted-foreground">
                {uploadPct}%
              </span>
            </div>
          )}
          {isOwn && (
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFileChange}
            />
          )}
          {(isOwn || canManageAvatar) && avatarMenu}
        </div>

        <div className="min-w-0 flex-1 space-y-1.5 pt-0.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={copyId}
              className="flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground hover:text-foreground"
              title="Скопировать ID"
            >
              ID: {profile.id}
              <Copy className="size-3" />
              {idCopied && <span className="text-[10px]">скопировано</span>}
            </button>

            {canEditRole ? (
              <Select
                value={roles?.find((r) => r.name === profile.role)?.id.toString() ?? ""}
                onValueChange={(v) => v && handleRoleChange(v)}
              >
                <SelectTrigger size="sm" className="h-6 w-auto gap-1 px-2 text-xs">
                  <SelectValue placeholder={profile.role ?? "—"} />
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
                <Badge variant="secondary">
                  {profile.role}
                  {isOwnerTarget && " — неприкасаема"}
                </Badge>
              )
            )}

            <Badge variant="outline" className="font-normal text-muted-foreground">
              на платформе с {fmtDate(profile.created_at)}
            </Badge>
            <Badge variant="outline" className="font-normal text-muted-foreground">
              обновлён {fmtDate(profile.updated_at)}
            </Badge>
          </div>
          {isOwn && uploadPct !== null && (
            <div className="w-56 space-y-1 pt-1">
              <Progress value={uploadPct} />
            </div>
          )}
          {isOwn && uploadPct === null && (
            <p className="text-xs text-muted-foreground">
              Нажмите на аватар или перетащите картинку, чтобы обновить (только фото)
            </p>
          )}
        </div>
      </div>

      <Separator />

      <div className="space-y-2">
        <p className="text-sm font-medium">Баланс</p>
        <div className="grid grid-cols-2 gap-2">
          <div className="flex items-center justify-between rounded-md border p-2.5">
            <div>
              <p className="text-xs text-muted-foreground">Основной</p>
              <p className="font-semibold tabular-nums">{profile.balance}</p>
            </div>
            {canAdjustBalance && !isOwnerTarget && (
              <Button size="icon-sm" variant="outline" onClick={() => setTopUpKind("main")}>
                <Wallet className="size-3.5" />
              </Button>
            )}
          </div>
          <div className="flex items-center justify-between rounded-md border p-2.5">
            <div>
              <p className="text-xs text-muted-foreground">Бонусный</p>
              <p className="font-semibold tabular-nums">{profile.bonus_balance}</p>
            </div>
            {canAdjustBalance && !isOwnerTarget && (
              <Button size="icon-sm" variant="outline" onClick={() => setTopUpKind("bonus")}>
                <Wallet className="size-3.5" />
              </Button>
            )}
          </div>
        </div>
      </div>

      <Separator />

      <div className="space-y-4">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium">Учётные данные</p>
          {profileDirty && (
            <Button type="button" size="sm" onClick={handleSaveProfile} disabled={savingProfile}>
              {savingProfile ? "Сохранение…" : "Сохранить"}
            </Button>
          )}
        </div>
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

        {isOwn && (!pwOpen ? (
          <Button type="button" size="sm" variant="outline" onClick={() => setPwOpen(true)}>
            <KeyRound className="size-3.5" />
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

      <Separator />

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">Реферальная программа</p>
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Users2 className="size-3.5" /> приглашено: {profile.referral_count}
          </span>
        </div>
        {referralLink ? (
          <div className="flex items-center gap-2">
            <Input readOnly value={referralLink} className="font-mono text-xs" />
            <Button type="button" size="icon-sm" variant="outline" onClick={copyReferralLink}>
              <Copy className="size-3.5" />
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">У аккаунта нет реферального кода.</p>
        )}
        {profile.referred_by_login && (
          <p className="text-xs text-muted-foreground">
            {isOwn ? "Вас пригласил" : "Пригласил"}:{" "}
            <span className="font-medium">{profile.referred_by_login}</span>
          </p>
        )}
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
