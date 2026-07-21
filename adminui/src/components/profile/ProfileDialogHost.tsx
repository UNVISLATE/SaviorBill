import { useRef, useState } from "react"
import { CreditCard, ImageIcon, PackageOpen, UserRound } from "lucide-react"
import { useQuery } from "@tanstack/react-query"

import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import { useIsMobile } from "@/hooks/use-mobile"
import { useProfileDialog } from "@/hooks/use-profile-dialog"
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
import { Button } from "@/components/shadsnui/button"
import { ProfileOverviewSection } from "@/components/profile/ProfileOverviewSection"
import { ProfileServicesSection } from "@/components/profile/ProfileServicesSection"
import { ProfilePaymentsSection } from "@/components/profile/ProfilePaymentsSection"
import { ProfileMediaSection, type MediaSectionHandle } from "@/components/profile/ProfileMediaSection"

type Section = "profile" | "services" | "payments" | "media"

const SECTIONS: { id: Section; title: string; icon: typeof UserRound }[] = [
  { id: "profile", title: "Профиль", icon: UserRound },
  { id: "media", title: "Медиа", icon: ImageIcon },
  { id: "services", title: "Товары/услуги", icon: PackageOpen },
  { id: "payments", title: "Платежи", icon: CreditCard },
]

function SectionContent({
  section,
  mode,
  userId,
  mediaRef,
}: {
  section: Section
  mode: "own" | "view"
  userId?: number
  mediaRef: React.Ref<MediaSectionHandle>
}) {
  if (section === "services") return <ProfileServicesSection mode={mode} userId={userId} />
  if (section === "payments") return <ProfilePaymentsSection mode={mode} userId={userId} />
  if (section === "media") return <ProfileMediaSection ref={mediaRef} mode={mode} userId={userId} />
  return <ProfileOverviewSection mode={mode} userId={userId} />
}

/** Внутренняя навигация профиля — колонка слева на десктопе, табы сверху в
 * шторке на мобильном. Общая для Dialog- и Drawer-варианта ниже. */
function ProfileNav({
  section,
  onSelect,
  orientation,
}: {
  section: Section
  onSelect: (s: Section) => void
  orientation: "vertical" | "horizontal"
}) {
  return (
    <nav
      className={cn(
        orientation === "vertical"
          ? "flex w-44 shrink-0 flex-col gap-1 border-r p-2"
          : "flex gap-1 border-b p-2"
      )}
    >
      {SECTIONS.map((s) => (
        <button
          key={s.id}
          type="button"
          onClick={() => onSelect(s.id)}
          className={cn(
            "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors",
            orientation === "horizontal" && "flex-1 justify-center",
            section === s.id
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
          )}
        >
          <s.icon className="size-4 shrink-0" />
          <span className={orientation === "horizontal" ? "hidden sm:inline" : undefined}>
            {s.title}
          </span>
        </button>
      ))}
    </nav>
  )
}

/** Диалог/шторка профиля — свой (через `openProfile()`, пункт "Профиль" в
 * NavUser) или чужой (через `openUserProfile(userId)`, например из таблицы
 * пользователей в админке) — общий layout, разный источник данных секций
 * (см. IMPLEMENTATION_PLAN.md §4). Монтируется один раз в App.tsx. */
export function ProfileDialogHost() {
  const { isOpen, target, closeProfile, isBusy } = useProfileDialog()
  const isMobile = useIsMobile()
  const [section, setSection] = useState<Section>("profile")
  const [dragActive, setDragActive] = useState(false)
  const mediaRef = useRef<MediaSectionHandle>(null)
  const mode = target.mode
  const userId = target.mode === "view" ? target.userId : undefined

  // Заголовок для чужого профиля — отдельный лёгкий запрос (не блокирует
  // рендер секций, которые грузят свои данные сами).
  const { data: viewedUser } = useQuery({
    queryKey: ["admin-user-brief", userId],
    queryFn: async () =>
      (await api.get<{ login: string }>(`/v1/admin/users/${userId}`)).data,
    enabled: mode === "view" && isOpen,
  })

  // Пока идёт загрузка аватарки (isBusy) — закрыть можно только явной
  // кнопкой "Закрыть", а не кликом снаружи/Esc/свайпом, чтобы не потерять
  // загрузку случайно.
  function handleOpenChange(open: boolean, eventDetails: { reason: string }) {
    if (!open && isBusy && eventDetails.reason !== "close-press") return
    if (!open) closeProfile()
  }

  const canDropFiles = section === "media" && mode === "own"

  // Drag&drop зоны вкладки "Медиа" — весь диалог/шторка целиком, а не только
  // блок с карточками (тот больше не привязан к своим onDrag*, см.
  // ProfileMediaSection). React-события перетаскивания всплывают как обычные
  // DOM-события, поэтому достаточно навесить их на внешний контейнер.
  //
  // ``types.includes("Files")`` — только у настоящего перетаскивания файлов
  // из ОС. Внутренний drag&drop сортировки превью (MediaPreviewGallery) тоже
  // всплывает сюда как обычный DragEvent, но без "Files" в dataTransfer —
  // без этой проверки любое перетаскивание превью внутри "Подробностей"
  // включало оверлей "Отпустите файл" и мешало сортировке.
  function isFileDrag(e: React.DragEvent): boolean {
    return Array.from(e.dataTransfer.types).includes("Files")
  }
  function onDragOver(e: React.DragEvent) {
    if (!canDropFiles || !isFileDrag(e)) return
    e.preventDefault()
    setDragActive(true)
  }
  function onDragLeave(e: React.DragEvent) {
    if (!canDropFiles || !isFileDrag(e)) return
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return
    setDragActive(false)
  }
  function onDrop(e: React.DragEvent) {
    if (!canDropFiles || !isFileDrag(e)) return
    e.preventDefault()
    setDragActive(false)
    if (e.dataTransfer.files?.length) mediaRef.current?.startUploads(e.dataTransfer.files)
  }

  const dropOverlay = dragActive && (
    <div className="pointer-events-none absolute inset-0 z-50 flex items-center justify-center rounded-[inherit] border-2 border-dashed border-foreground/50 bg-foreground/5">
      <span className="rounded-md bg-popover px-3 py-1.5 text-sm font-medium shadow-lg ring-1 ring-foreground/10">
        Отпустите файл, чтобы загрузить
      </span>
    </div>
  )

  const drawerTitle = mode === "view" ? `Профиль: ${viewedUser?.login ?? "…"}` : "Профиль"

  if (isMobile) {
    return (
      <Drawer open={isOpen} onOpenChange={handleOpenChange} disablePointerDismissal={isBusy}>
        <DrawerContent
          className="h-[85vh]"
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
        >
          <DrawerHeader className="flex items-center justify-between">
            <DrawerTitle>{drawerTitle}</DrawerTitle>
            <DrawerClose render={<Button variant="ghost" size="sm" />}>Закрыть</DrawerClose>
          </DrawerHeader>
          <ProfileNav section={section} onSelect={setSection} orientation="horizontal" />
          <div className="flex-1 overflow-y-auto p-4">
            <SectionContent section={section} mode={mode} userId={userId} mediaRef={mediaRef} />
          </div>
          {dropOverlay}
        </DrawerContent>
      </Drawer>
    )
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange} disablePointerDismissal={isBusy}>
      <DialogContent
        className="flex h-[640px] max-w-3xl gap-0 overflow-hidden p-0 sm:max-w-3xl"
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <ProfileNav section={section} onSelect={setSection} orientation="vertical" />
        <div className="flex-1 overflow-y-auto p-6">
          <DialogHeader className="mb-4">
            <DialogTitle>
              {mode === "view"
                ? `${SECTIONS.find((s) => s.id === section)?.title} — ${viewedUser?.login ?? "…"}`
                : SECTIONS.find((s) => s.id === section)?.title}
            </DialogTitle>
          </DialogHeader>
          <SectionContent section={section} mode={mode} userId={userId} mediaRef={mediaRef} />
        </div>
        {dropOverlay}
      </DialogContent>
    </Dialog>
  )
}
