import { useState, useRef, useEffect, useCallback, type DragEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  CreditCard,
  ImageIcon,
  PackageOpen,
  ShieldAlert,
  ShieldCheck,
  Ticket,
  UserRound,
  UsersRound,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { toastError, toastSuccess } from "@/lib/toast.ts"
import { useIsMobile } from "@/hooks/use-mobile"
import { useProfileDialog } from "@/hooks/use-profile-dialog"
import { cn } from "@/lib/utils.ts"
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
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from "@/components/shadsnui/drawer"
import { Input } from "@/components/shadsnui/input"
import { Button } from "@/components/shadsnui/button"
import { CreateUserSection } from "@/components/profile/CreateUserSection"
import { ProfileOverviewSection } from "@/components/profile/ProfileOverviewSection"
import { ProfileServicesSection } from "@/components/profile/ProfileServicesSection"
import { ProfilePaymentsSection } from "@/components/profile/ProfilePaymentsSection"
import { ProfileMediaSection, type MediaSectionHandle } from "@/components/profile/ProfileMediaSection"
import { ProfilePromocodesSection } from "@/components/profile/ProfilePromocodesSection"
import { ProfileReferralsSection } from "@/components/profile/ProfileReferralsSection"
import { ProfileSessionsSection } from "@/components/profile/ProfileSessionsSection"
import { ProfileTwoFASection } from "@/components/profile/ProfileTwoFASection"

type Section =
  | "profile"
  | "services"
  | "payments"
  | "media"
  | "promocodes"
  | "referrals"
  | "sessions"
  | "security"

const ALL_SECTIONS: {
  id: Section
  title: string
  icon: typeof UserRound
  viewOnly?: boolean
  ownOnly?: boolean
}[] = [
  { id: "profile", title: "Профиль", icon: UserRound },
  { id: "media", title: "Медиа", icon: ImageIcon },
  { id: "services", title: "Товары/услуги", icon: PackageOpen },
  { id: "payments", title: "Платежи", icon: CreditCard },
  { id: "promocodes", title: "Промокоды", icon: Ticket, viewOnly: true },
  { id: "referrals", title: "Реферальная программа", icon: UsersRound },
  { id: "sessions", title: "Сессии", icon: ShieldAlert },
  { id: "security", title: "Безопасность", icon: ShieldCheck, ownOnly: true },
]

function SectionContent({
  section,
  mode,
  userId,
  mediaRef,
  onCreated,
  onCancel,
  onDeleteClick,
}: {
  section: Section
  mode: "own" | "view" | "create"
  userId?: number
  mediaRef: React.Ref<MediaSectionHandle>
  onCreated: (newUserId: number) => void
  onCancel: () => void
  onDeleteClick?: () => void
}) {
  if (mode === "create") {
    return <CreateUserSection onCreated={onCreated} onCancel={onCancel} />
  }
  if (section === "services") return <ProfileServicesSection mode={mode} userId={userId} />
  if (section === "payments") return <ProfilePaymentsSection mode={mode} userId={userId} />
  if (section === "media") return <ProfileMediaSection ref={mediaRef} mode={mode} userId={userId} />
  if (section === "promocodes") return <ProfilePromocodesSection userId={userId} />
  if (section === "referrals") return <ProfileReferralsSection mode={mode} userId={userId} />
  if (section === "sessions") return <ProfileSessionsSection userId={userId} mode={mode} />
  if (section === "security") return <ProfileTwoFASection />
  return <ProfileOverviewSection mode={mode} userId={userId} onDeleteClick={onDeleteClick} />
}

/** Внутренняя навигация профиля — колонка слева на десктопе, табы сверху в
 * шторке на мобильном. Общая для Dialog- и Drawer-варианта ниже. */
function ProfileNav({
  sections,
  section,
  onSelect,
  orientation,
}: {
  sections: typeof ALL_SECTIONS
  section: Section
  onSelect: (s: Section) => void
  orientation: "vertical" | "horizontal"
}) {
  return (
    <nav
      className={cn(
        orientation === "vertical"
          ? "flex w-48 shrink-0 flex-col gap-1 border-r bg-muted/30 p-3"
          : "flex shrink-0 gap-1 overflow-x-auto border-b bg-muted/30 p-2",
      )}
    >
      {sections.map((s) => {
        const Icon = s.icon
        const active = section === s.id
        return (
          <button
            key={s.id}
            type="button"
            onClick={() => onSelect(s.id)}
            className={cn(
              "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors",
              active
                ? "bg-accent font-medium text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
            )}
          >
            <Icon className="size-4 shrink-0" />
            <span className="truncate">{s.title}</span>
          </button>
        )
      })}
    </nav>
  )
}

/** Имя события, которое генерирует перехватчик 403 totp_setup_required в
 * api.ts. Вынесено константой, чтобы не опечататься. */
export const TOTP_SETUP_REQUIRED_EVENT = "saviorbill:totp_setup_required"

/** Диалог подтверждения удаления чужого пользователя */
function DeleteUserDialog({
  userId,
  login,
  open,
  onOpenChange,
}: {
  userId: number
  login: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [confirmText, setConfirmText] = useState("")
  const qc = useQueryClient()
  const { closeProfile } = useProfileDialog()

  const del = useMutation({
    mutationFn: async () => api.delete(`/v1/admin/users/${userId}`),
    onSuccess: () => {
      toastSuccess(`Пользователь «${login}» удалён`)
      onOpenChange(false)
      closeProfile()
      void qc.invalidateQueries({ queryKey: ["admin-users"] })
      void qc.invalidateQueries({ queryKey: ["admin-users-stats"] })
      void qc.invalidateQueries({ queryKey: ["admin-users-stats-by-day"] })
    },
    onError: (e: unknown) => {
      toastError("Не удалось удалить пользователя", getErrorDetail(e))
    },
  })

  return (
    <AlertDialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) setConfirmText("") }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Удалить пользователя?</AlertDialogTitle>
          <AlertDialogDescription>
            Действие необратимо: удалятся услуги, платежи, OAuth-привязки и
            активации промокодов этого пользователя. Введите{" "}
            <code className="rounded bg-muted px-1 py-0.5 select-all">{login}</code>{" "}
            для подтверждения.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <Input
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          placeholder="введите логин"
          autoFocus
        />
        <AlertDialogFooter>
          <AlertDialogCancel>Отмена</AlertDialogCancel>
          <AlertDialogAction
            disabled={confirmText !== login || del.isPending}
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

/** Диалог/шторка профиля — свой (через `openProfile()`, пункт "Профиль" в
 * NavUser) или чужой (через `openUserProfile(userId)`, например из таблицы
 * пользователей в админке). Монтируется один раз в App.tsx. */
export function ProfileDialogHost() {
  const { isOpen, target, closeProfile, isBusy, openProfile, openUserProfile } = useProfileDialog()
  const isMobile = useIsMobile()
  const qc = useQueryClient()
  const [dragActive, setDragActive] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const mediaRef = useRef<MediaSectionHandle>(null)
  const mode = target.mode
  const userId = target.mode === "view" ? target.userId : undefined

  const revokeAllSessions = useMutation({
    mutationFn: async () => {
      const basePath = mode === "own" ? "/v1/user/me/sessions" : `/v1/admin/users/${userId}/sessions`
      await api.delete(basePath)
    },
    onSuccess: () => {
      toastSuccess("Все сессии завершены")
      void qc.invalidateQueries({
        queryKey: [mode === "own" ? "my-sessions" : "admin-user-sessions", userId],
      })
    },
    onError: (e) => toastError("Не удалось завершить сессии", getErrorDetail(e)),
  })

  const sections = ALL_SECTIONS.filter(
    (s) => (!s.viewOnly || mode === "view") && (!s.ownOnly || mode === "own"),
  )

  // Изоляция состояния вкладок по контексту: свой профиль ("own"), создание ("create")
  // и каждый отдельный пользователь ("user:4") хранят свои активные вкладки независимо.
  const contextKey = mode === "view" ? `user:${userId}` : mode === "create" ? "create" : "own"
  const [tabsByContext, setTabsByContext] = useState<Record<string, Section>>({})

  const rawSection = tabsByContext[contextKey] ?? "profile"
  const section: Section = sections.some((s) => s.id === rawSection) ? rawSection : "profile"

  const setSection = useCallback((s: Section) => {
    setTabsByContext((prev) => ({ ...prev, [contextKey]: s }))
  }, [contextKey, setTabsByContext])

  // 403 totp_setup_required
  useEffect(() => {
    function onTotpRequired() {
      openProfile()
      setSection("security")
      toastError(
        "Нужна двухфакторная аутентификация",
        "Для вашей роли она обязательна настройкой инстанса — включите её здесь, чтобы продолжить работать в админке.",
      )
    }
    window.addEventListener(TOTP_SETUP_REQUIRED_EVENT, onTotpRequired)
    return () => window.removeEventListener(TOTP_SETUP_REQUIRED_EVENT, onTotpRequired)
  }, [openProfile, setSection])

  // Заголовок для чужого профиля
  const { data: viewedUser } = useQuery({
    queryKey: ["admin-user-brief", userId],
    queryFn: async () =>
      (await api.get<{ login: string; role: string | null }>(`/v1/admin/users/${userId}/profile`)).data,
    enabled: mode === "view" && isOpen,
  })

  function handleOpenChange(open: boolean, eventDetails?: { reason?: string }) {
    if (!open && isBusy && eventDetails?.reason !== "close-press") return
    if (!open) closeProfile()
  }

  const canDropFiles = section === "media" && mode === "own"

  function onDragOver(e: DragEvent<HTMLDivElement>) {
    if (!canDropFiles) return
    if (!e.dataTransfer.types.includes("Files")) return
    e.preventDefault()
    e.stopPropagation()
    setDragActive(true)
  }

  function onDragLeave(e: DragEvent<HTMLDivElement>) {
    if (!canDropFiles) return
    e.preventDefault()
    e.stopPropagation()
    const targetEl = e.currentTarget
    const related = e.relatedTarget as Node | null
    if (related && targetEl.contains(related)) return
    setDragActive(false)
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    if (!canDropFiles) return
    if (!e.dataTransfer.types.includes("Files")) return
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) {
      mediaRef.current?.startUploads(files)
    }
  }

  const dropOverlay = dragActive && canDropFiles && (
    <div className="pointer-events-none absolute inset-0 z-50 flex items-center justify-center rounded-[inherit] border-2 border-dashed border-foreground/50 bg-foreground/5">
      <span className="rounded-md bg-popover px-3 py-1.5 text-sm font-medium shadow-lg ring-1 ring-foreground/10">
        Отпустите файл, чтобы загрузить
      </span>
    </div>
  )

  // РЕЖИМ СОЗДАНИЯ: компактное окно без боковой панели вкладок (1 вкладка)
  if (mode === "create") {
    if (isMobile) {
      return (
        <Drawer open={isOpen} onOpenChange={handleOpenChange} disablePointerDismissal={isBusy}>
          <DrawerContent className="p-4">
            <DrawerHeader className="mb-2 flex items-center justify-between">
              <DrawerTitle>Новый пользователь</DrawerTitle>
              <DrawerClose render={<Button variant="ghost" size="sm" />}>Закрыть</DrawerClose>
            </DrawerHeader>
            <CreateUserSection onCreated={openUserProfile} onCancel={closeProfile} />
          </DrawerContent>
        </Drawer>
      )
    }

    return (
      <Dialog open={isOpen} onOpenChange={handleOpenChange} disablePointerDismissal={isBusy}>
        <DialogContent className="max-w-md p-6 sm:max-w-lg">
          <DialogHeader className="mb-2">
            <DialogTitle>Создание пользователя</DialogTitle>
          </DialogHeader>
          <CreateUserSection onCreated={openUserProfile} onCancel={closeProfile} />
        </DialogContent>
      </Dialog>
    )
  }

  const drawerTitle = mode === "view" ? `Профиль: ${viewedUser?.login ?? "…"}` : "Профиль"

  if (isMobile) {
    return (
      <>
        <Drawer open={isOpen} onOpenChange={handleOpenChange} disablePointerDismissal={isBusy}>
          <DrawerContent
            className="h-[85vh]"
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
          >
            <DrawerHeader className="flex items-center justify-between gap-2">
              <DrawerTitle className="truncate">{drawerTitle}</DrawerTitle>
              <div className="flex items-center gap-2">
                {section === "sessions" && (
                  <Button
                    type="button"
                    size="xs"
                    variant="outline"
                    className="h-7 text-xs text-destructive border-destructive/30"
                    disabled={revokeAllSessions.isPending}
                    onClick={() => revokeAllSessions.mutate()}
                  >
                    Завершить все
                  </Button>
                )}
                <DrawerClose render={<Button variant="ghost" size="sm" />}>Закрыть</DrawerClose>
              </div>
            </DrawerHeader>
            <ProfileNav sections={sections} section={section} onSelect={setSection} orientation="horizontal" />
            <div className="flex-1 overflow-y-auto p-4">
              <SectionContent
                section={section}
                mode={mode}
                userId={userId}
                mediaRef={mediaRef}
                onCreated={openUserProfile}
                onCancel={closeProfile}
                onDeleteClick={() => setDeleteDialogOpen(true)}
              />
            </div>
            {dropOverlay}
          </DrawerContent>
        </Drawer>
        {viewedUser && userId && (
          <DeleteUserDialog
            userId={userId}
            login={viewedUser.login}
            open={deleteDialogOpen}
            onOpenChange={setDeleteDialogOpen}
          />
        )}
      </>
    )
  }

  return (
    <>
      <Dialog open={isOpen} onOpenChange={handleOpenChange} disablePointerDismissal={isBusy}>
        <DialogContent
          className="flex h-[640px] max-w-3xl gap-0 overflow-hidden p-0 sm:max-w-3xl"
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
        >
          <ProfileNav sections={sections} section={section} onSelect={setSection} orientation="vertical" />
          <div className="flex-1 overflow-y-auto p-6">
            <DialogHeader className="mb-4 flex flex-row items-center justify-between gap-3 space-y-0 pr-8">
              <DialogTitle className="truncate">
                {mode === "view"
                  ? `${sections.find((s) => s.id === section)?.title} — ${viewedUser?.login ?? "…"}`
                  : sections.find((s) => s.id === section)?.title}
              </DialogTitle>
              {section === "sessions" && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-7 shrink-0 text-xs text-destructive border-destructive/30 hover:bg-destructive/10 hover:text-destructive"
                  disabled={revokeAllSessions.isPending}
                  onClick={() => revokeAllSessions.mutate()}
                >
                  Завершить все
                </Button>
              )}
            </DialogHeader>
            <SectionContent
              section={section}
              mode={mode}
              userId={userId}
              mediaRef={mediaRef}
              onCreated={openUserProfile}
              onCancel={closeProfile}
              onDeleteClick={() => setDeleteDialogOpen(true)}
            />
          </div>
          {dropOverlay}
        </DialogContent>
      </Dialog>
      {viewedUser && userId && (
        <DeleteUserDialog
          userId={userId}
          login={viewedUser.login}
          open={deleteDialogOpen}
          onOpenChange={setDeleteDialogOpen}
        />
      )}
    </>
  )
}
