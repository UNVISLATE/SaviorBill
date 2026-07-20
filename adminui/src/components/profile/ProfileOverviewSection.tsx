import { useRef, useState } from "react"
import { Check, Copy, Loader2, Upload } from "lucide-react"

import { useProfileDialog } from "@/hooks/use-profile-dialog"
import { useInvalidateUserProfile, useUserProfile } from "@/hooks/use-user-profile"
import { useAuth } from "@/hooks/use-auth"
import { api } from "@/lib/api"
import { uploadOwnMedia } from "@/lib/media-upload"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/shadsnui/avatar"
import { Button } from "@/components/shadsnui/button"
import { Field, FieldLabel } from "@/components/shadsnui/field"
import { Input } from "@/components/shadsnui/input"
import { Progress } from "@/components/shadsnui/progress"
import { Separator } from "@/components/shadsnui/separator"
import { Skeleton } from "@/components/shadsnui/skeleton"

function initials(login: string): string {
  return login.slice(0, 2).toUpperCase()
}

export function ProfileOverviewSection() {
  const { data: profile, isLoading } = useUserProfile()
  const invalidateProfile = useInvalidateUserProfile()
  const { me } = useAuth()
  const { setBusy } = useProfileDialog()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [uploadPct, setUploadPct] = useState<number | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const [login, setLogin] = useState("")
  const [email, setEmail] = useState("")
  const [savingProfile, setSavingProfile] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveOk, setSaveOk] = useState(false)
  const [copied, setCopied] = useState(false)

  // Синхронизируем локальные поля формы, когда профиль подгрузился впервые
  // (не на каждый рендер — иначе затирали бы то, что юзер уже вводит).
  const [synced, setSynced] = useState(false)
  if (profile && !synced) {
    setLogin(profile.login)
    setEmail(profile.email ?? "")
    setSynced(true)
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return

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

  const referralLink = profile?.ref_code
    ? `${window.location.origin}/r/${profile.ref_code}`
    : null

  async function copyReferralLink() {
    if (!referralLink) return
    await navigator.clipboard.writeText(referralLink)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

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
      <div className="flex items-center gap-4">
        <div className="relative">
          <Avatar className="size-20">
            {profile.avatar_url && <AvatarImage src={profile.avatar_url} alt="" />}
            <AvatarFallback className="text-lg">
              {initials(me?.login ?? profile.login)}
            </AvatarFallback>
          </Avatar>
          {uploadPct !== null && (
            <div className="absolute inset-0 flex items-center justify-center rounded-full bg-background/70">
              <Loader2 className="size-6 animate-spin text-primary" />
            </div>
          )}
        </div>
        <div className="space-y-1.5">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadPct !== null}
          >
            <Upload className="size-3.5" />
            Загрузить аватар
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFileChange}
          />
          {uploadPct !== null && (
            <div className="w-48 space-y-1">
              <Progress value={uploadPct} />
              <p className="text-xs text-muted-foreground">Загрузка… {uploadPct}%</p>
            </div>
          )}
          {uploadError && <p className="text-xs text-destructive">{uploadError}</p>}
        </div>
      </div>

      <Separator />

      <div className="space-y-4">
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
        <div className="flex items-center gap-2">
          <Button type="button" size="sm" onClick={handleSaveProfile} disabled={savingProfile}>
            {savingProfile ? "Сохранение…" : "Сохранить"}
          </Button>
          {saveOk && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Check className="size-3.5" /> Сохранено
            </span>
          )}
        </div>
      </div>

      <Separator />

      <div className="space-y-2">
        <p className="text-sm font-medium">Реферальная ссылка</p>
        {referralLink ? (
          <div className="flex items-center gap-2">
            <Input readOnly value={referralLink} className="font-mono text-xs" />
            <Button type="button" size="icon-sm" variant="outline" onClick={copyReferralLink}>
              {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            У аккаунта нет реферального кода.
          </p>
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
