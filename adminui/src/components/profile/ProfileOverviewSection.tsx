import { useRef, useState, type ChangeEvent, type DragEvent } from "react"
import { Camera, Check, Copy, KeyRound, Loader2, Users2 } from "lucide-react"

import { useProfileDialog } from "@/hooks/use-profile-dialog"
import { useInvalidateUserProfile, useUserProfile } from "@/hooks/use-user-profile"
import { useAuth } from "@/hooks/use-auth"
import { api } from "@/lib/api"
import { uploadOwnMedia } from "@/lib/media-upload"
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

export function ProfileOverviewSection() {
  const { data: profile, isLoading } = useUserProfile()
  const invalidateProfile = useInvalidateUserProfile()
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
  const [synced, setSynced] = useState(false)
  if (profile && !synced) {
    setLogin(profile.login)
    setEmail(profile.email ?? "")
    setSynced(true)
  }

  async function doUpload(file: File) {
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
      const patch: Record<string, string> = {}
      if (login !== profile.login) patch.login = login
      if (email !== (profile.email ?? "")) patch.email = email
      if (Object.keys(patch).length > 0) {
        await api.patch("/v1/user/me", patch)
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

  const profileDirty = !!profile && (login !== profile.login || email !== (profile.email ?? ""))

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
          className="group relative shrink-0 cursor-pointer"
          onClick={() => uploadPct === null && fileInputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <Avatar
            className={
              "size-20 ring-2 ring-offset-2 ring-offset-background transition-all " +
              (dragOver ? "ring-primary" : "ring-transparent group-hover:ring-border")
            }
          >
            {profile.avatar_url && <AvatarImage src={profile.avatar_url} alt="" />}
            <AvatarFallback className="text-lg">
              {initials(me?.login ?? profile.login)}
            </AvatarFallback>
          </Avatar>
          <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/0 text-transparent transition-colors group-hover:bg-black/40 group-hover:text-white">
            <Camera className="size-5" />
          </div>
          {uploadPct !== null && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 rounded-full bg-background/85">
              <Loader2 className="size-5 animate-spin text-primary" />
              <span className="text-[10px] font-medium tabular-nums text-muted-foreground">
                {uploadPct}%
              </span>
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFileChange}
          />
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
          {uploadPct !== null && (
            <div className="w-56 space-y-1 pt-1">
              <Progress value={uploadPct} />
            </div>
          )}
          {uploadError && <p className="text-xs text-destructive">{uploadError}</p>}
          {uploadPct === null && !uploadError && (
            <p className="text-xs text-muted-foreground">
              Нажмите на аватар или перетащите картинку, чтобы обновить (только фото)
            </p>
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
          <Input id="profile-login" value={login} onChange={(e) => setLogin(e.target.value)} />
        </Field>
        <Field>
          <FieldLabel htmlFor="profile-email">Email</FieldLabel>
          <Input
            id="profile-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        {saveError && <p className="text-sm text-destructive">{saveError}</p>}

        {!pwOpen ? (
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
        )}
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
            Вас пригласил: <span className="font-medium">{profile.referred_by_login}</span>
          </p>
        )}
      </div>
    </div>
  )
}
