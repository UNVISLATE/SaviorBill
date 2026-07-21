import { useRef, useState, type ChangeEvent, type DragEvent } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Camera, Check, Copy, KeyRound, Loader2, Users2 } from "lucide-react"

import { useProfileDialog } from "@/hooks/use-profile-dialog"
import { useInvalidateUserProfile, useUserProfile, type UserProfile } from "@/hooks/use-user-profile"
import { useAuth } from "@/hooks/use-auth"
import { api } from "@/api/api.ts"
import { uploadOwnMedia } from "@/api/media-upload.ts"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/shadsnui/avatar"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Field, FieldLabel } from "@/components/shadsnui/field"
import { Input } from "@/components/shadsnui/input"
import { Progress } from "@/components/shadsnui/progress"
import { Separator } from "@/components/shadsnui/separator"
import { Skeleton } from "@/components/shadsnui/skeleton"

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
  const canEditEmail = isOwn || can("users.edit")
  const canManageAvatar = isOwn || can("admin.media.manage_any")

  const { me } = useAuth()
  const { setBusy } = useProfileDialog()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [uploadPct, setUploadPct] = useState<number | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)

  const [login, setLogin] = useState("")
  const [email, setEmail] = useState("")
  const [savingProfile, setSavingProfile] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveOk, setSaveOk] = useState(false)
  const [copied, setCopied] = useState(false)

  const [pwOpen, setPwOpen] = useState(false)
  const [pwCurrent, setPwCurrent] = useState("")
  const [pwNew, setPwNew] = useState("")
  const [pwSaving, setPwSaving] = useState(false)
  const [pwError, setPwError] = useState<string | null>(null)
  const [pwOk, setPwOk] = useState(false)

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
    setUploadError(null)
    setUploadPct(0)
    setBusy(true)
    try {
      const { mediaId } = await uploadOwnMedia(file, {
        tag: "avatar",
        onProgress: (p) => setUploadPct(Math.round((p.loaded / Math.max(p.total, 1)) * 100)),
      })
      await api.put("/v1/user/me/avatar", { media_id: mediaId })
      invalidateProfile()
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "не удалось загрузить аватар")
    } finally {
      setUploadPct(null)
      setBusy(false)
    }
  }

  async function clearAvatar() {
    if (isOwn || !userId) return
    setBusy(true)
    try {
      await api.put(`/v1/admin/users/${userId}/avatar`, { media_id: null })
      invalidateProfile()
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
    setSaveError(null)
    setSaveOk(false)
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
      setSaveOk(true)
    } catch {
      setSaveError("не удалось сохранить — логин/email могут быть уже заняты")
    } finally {
      setSavingProfile(false)
    }
  }

  async function handleChangePassword() {
    setPwSaving(true)
    setPwError(null)
    setPwOk(false)
    try {
      await api.post("/v1/user/me/password", {
        current_password: pwCurrent || undefined,
        new_password: pwNew,
      })
      setPwOk(true)
      setPwCurrent("")
      setPwNew("")
    } catch {
      setPwError("не удалось сменить пароль — проверьте текущий пароль")
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
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
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
        </div>

        <div className="min-w-0 flex-1 space-y-1.5 pt-0.5">
          <div className="flex flex-wrap items-center gap-1.5">
            {profile.role && <Badge variant="secondary">{profile.role}</Badge>}
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
          {isOwn && uploadError && <p className="text-xs text-destructive">{uploadError}</p>}
          {isOwn && uploadPct === null && !uploadError && (
            <p className="text-xs text-muted-foreground">
              Нажмите на аватар или перетащите картинку, чтобы обновить (только фото)
            </p>
          )}
          {!isOwn && canManageAvatar && profile.avatar_url && (
            <Button type="button" size="sm" variant="outline" onClick={clearAvatar}>
              Сбросить аватар
            </Button>
          )}
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
          {saveOk && !profileDirty && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Check className="size-3.5" /> Сохранено
            </span>
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
        {saveError && <p className="text-sm text-destructive">{saveError}</p>}

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
            {pwError && <p className="text-sm text-destructive">{pwError}</p>}
            {pwOk && (
              <p className="flex items-center gap-1 text-xs text-muted-foreground">
                <Check className="size-3.5" /> Пароль изменён
              </p>
            )}
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
                  setPwError(null)
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
              {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
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
    </div>
  )
}
