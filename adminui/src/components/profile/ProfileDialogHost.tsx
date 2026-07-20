import { useState } from "react"
import { CreditCard, ImageIcon, PackageOpen, UserRound } from "lucide-react"

import { cn } from "@/lib/utils"
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
import { ProfileMediaSection } from "@/components/profile/ProfileMediaSection"

type Section = "profile" | "services" | "payments" | "media"

const SECTIONS: { id: Section; title: string; icon: typeof UserRound }[] = [
  { id: "profile", title: "Профиль", icon: UserRound },
  { id: "media", title: "Медиа", icon: ImageIcon },
  { id: "services", title: "Товары/услуги", icon: PackageOpen },
  { id: "payments", title: "Платежи", icon: CreditCard },
]

function SectionContent({ section }: { section: Section }) {
  if (section === "services") return <ProfileServicesSection />
  if (section === "payments") return <ProfilePaymentsSection />
  if (section === "media") return <ProfileMediaSection />
  return <ProfileOverviewSection />
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

/** Диалог/шторка редактирования собственного профиля админа — монтируется
 * один раз в App.tsx, открывается через useProfileDialog().openProfile()
 * (сейчас вызывается из пункта "Профиль" в NavUser). */
export function ProfileDialogHost() {
  const { isOpen, closeProfile, isBusy } = useProfileDialog()
  const isMobile = useIsMobile()
  const [section, setSection] = useState<Section>("profile")

  // Пока идёт загрузка аватарки (isBusy) — закрыть можно только явной
  // кнопкой "Закрыть", а не кликом снаружи/Esc/свайпом, чтобы не потерять
  // загрузку случайно.
  function handleOpenChange(open: boolean, eventDetails: { reason: string }) {
    if (!open && isBusy && eventDetails.reason !== "close-press") return
    if (!open) closeProfile()
  }

  if (isMobile) {
    return (
      <Drawer open={isOpen} onOpenChange={handleOpenChange} disablePointerDismissal={isBusy}>
        <DrawerContent className="h-[85vh]">
          <DrawerHeader className="flex items-center justify-between">
            <DrawerTitle>Профиль</DrawerTitle>
            <DrawerClose render={<Button variant="ghost" size="sm" />}>Закрыть</DrawerClose>
          </DrawerHeader>
          <ProfileNav section={section} onSelect={setSection} orientation="horizontal" />
          <div className="flex-1 overflow-y-auto p-4">
            <SectionContent section={section} />
          </div>
        </DrawerContent>
      </Drawer>
    )
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange} disablePointerDismissal={isBusy}>
      <DialogContent className="flex h-[640px] max-w-3xl gap-0 overflow-hidden p-0 sm:max-w-3xl">
        <ProfileNav section={section} onSelect={setSection} orientation="vertical" />
        <div className="flex-1 overflow-y-auto p-6">
          <DialogHeader className="mb-4">
            <DialogTitle>{SECTIONS.find((s) => s.id === section)?.title}</DialogTitle>
          </DialogHeader>
          <SectionContent section={section} />
        </div>
      </DialogContent>
    </Dialog>
  )
}
