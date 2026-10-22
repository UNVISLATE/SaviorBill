import { useState, useEffect, useRef, type ReactNode, type ComponentType } from "react"
import { useIsMobile } from "@/hooks/use-mobile"
import { cn } from "@/lib/utils.ts"
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

export interface TabbedDialogTab {
  id: string
  title?: string
  label?: string
  icon?: ComponentType<{ className?: string }>
  badge?: ReactNode
  disabled?: boolean
  content?: ReactNode
}

export type TabDefinition = TabbedDialogTab

export interface DialogAction {
  label: string
  onClick: () => void
  disabled?: boolean
  loading?: boolean
  variant?: "default" | "destructive" | "outline" | "secondary" | "ghost"
}

export interface TabbedDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: ReactNode
  description?: ReactNode
  tabs: TabbedDialogTab[]
  activeTab?: string
  onTabChange?: (tabId: string) => void
  children?: ReactNode
  headerActions?: ReactNode
  footer?: ReactNode
  primaryAction?: DialogAction
  secondaryAction?: DialogAction
  maxWidth?: string // e.g. "max-w-3xl", "max-w-4xl" (default: "max-w-3xl")
  height?: string // e.g. "h-[640px]", "h-[700px]" (default: "h-[640px]")
  disablePointerDismissal?: boolean
  className?: string
}

export function TabbedDialog({
  open,
  onOpenChange,
  title,
  description,
  tabs,
  activeTab: controlledActiveTab,
  onTabChange: controlledOnTabChange,
  children,
  headerActions,
  footer,
  primaryAction,
  secondaryAction,
  maxWidth = "w-full max-w-3xl sm:max-w-3xl",
  height = "h-[640px]",
  disablePointerDismissal,
  className,
}: TabbedDialogProps) {
  const isMobile = useIsMobile()
  const [internalActiveTab, setInternalActiveTab] = useState(tabs[0]?.id || "")
  const prevOpenRef = useRef(open)

  useEffect(() => {
    if (!prevOpenRef.current && open && tabs.length > 0) {
      if (!controlledActiveTab) {
        setInternalActiveTab(tabs[0].id)
      }
    }
    prevOpenRef.current = open
  }, [open, controlledActiveTab])

  const activeTabId = controlledActiveTab !== undefined ? controlledActiveTab : internalActiveTab
  const handleTabChange = (id: string) => {
    if (controlledOnTabChange) {
      controlledOnTabChange(id)
    } else {
      setInternalActiveTab(id)
    }
  }

  const activeTabObj = tabs.find((t) => t.id === activeTabId) || tabs[0]
  const currentContent = children !== undefined ? children : activeTabObj?.content

  // Формируем footer, если переданы primaryAction / secondaryAction
  let renderedFooter = footer
  if (!renderedFooter && (primaryAction || secondaryAction)) {
    renderedFooter = (
      <div className="flex w-full items-center justify-end gap-2">
        {secondaryAction && (
          <Button
            type="button"
            variant={secondaryAction.variant || "outline"}
            size="sm"
            onClick={secondaryAction.onClick}
            disabled={secondaryAction.disabled}
          >
            {secondaryAction.label}
          </Button>
        )}
        {primaryAction && (
          <Button
            type="button"
            variant={primaryAction.variant || "default"}
            size="sm"
            onClick={primaryAction.onClick}
            disabled={primaryAction.disabled || primaryAction.loading}
          >
            {primaryAction.loading ? "Сохранение..." : primaryAction.label}
          </Button>
        )}
      </div>
    )
  }

  const navContent = (orientation: "vertical" | "horizontal") => (
    <nav
      className={cn(
        orientation === "vertical"
          ? "flex w-52 shrink-0 flex-col gap-1 border-r border-border/80 bg-muted/20 p-3"
          : "flex shrink-0 gap-1 overflow-x-auto border-b border-border/80 bg-muted/20 p-2",
      )}
    >
      {tabs.map((t) => {
        const Icon = t.icon
        const active = activeTabId === t.id
        const tabTitle = t.label || t.title || t.id
        return (
          <button
            key={t.id}
            type="button"
            disabled={t.disabled}
            onClick={() => handleTabChange(t.id)}
            className={cn(
              "flex items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm transition-all cursor-pointer",
              active
                ? "bg-accent font-medium text-accent-foreground shadow-2xs"
                : "text-muted-foreground hover:bg-accent/40 hover:text-foreground",
              t.disabled && "opacity-50 cursor-not-allowed pointer-events-none",
            )}
          >
            <div className="flex items-center gap-2 truncate">
              {Icon && <Icon className="size-4 shrink-0" />}
              <span className="truncate">{tabTitle}</span>
            </div>
            {t.badge && (
              <span className="shrink-0 text-xs text-muted-foreground">
                {t.badge}
              </span>
            )}
          </button>
        )
      })}
    </nav>
  )

  if (isMobile) {
    return (
      <Drawer
        open={open}
        onOpenChange={onOpenChange}
        disablePointerDismissal={disablePointerDismissal}
      >
        <DrawerContent className={cn("max-h-[90vh] flex flex-col p-0", className)}>
          <DrawerHeader className="flex items-center justify-between gap-2 border-b border-border/80 px-4 py-3">
            <div className="min-w-0 flex-1">
              <DrawerTitle className="truncate text-base font-semibold">
                {title}
              </DrawerTitle>
              {description && (
                <div className="text-xs text-muted-foreground truncate">
                  {description}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              {headerActions}
              <DrawerClose render={<Button variant="ghost" size="sm" />}>
                Закрыть
              </DrawerClose>
            </div>
          </DrawerHeader>

          {navContent("horizontal")}

          <div className="flex-1 overflow-y-auto p-4">{currentContent}</div>

          {renderedFooter && (
            <div className="border-t border-border/80 bg-background/95 px-4 py-3 backdrop-blur-xs">
              {renderedFooter}
            </div>
          )}
        </DrawerContent>
      </Drawer>
    )
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      disablePointerDismissal={disablePointerDismissal}
    >
      <DialogContent
        className={cn(
          "flex gap-0 overflow-hidden p-0 shadow-xl border-border/80",
          height,
          maxWidth,
          className,
        )}
      >
        {navContent("vertical")}

        <div className="flex flex-1 flex-col overflow-hidden min-w-0">
          <DialogHeader className="flex flex-row items-center justify-between gap-3 border-b border-border/60 px-6 py-4 space-y-0 pr-12">
            <div className="min-w-0 flex-1">
              <DialogTitle className="truncate text-base font-semibold">
                {title}
              </DialogTitle>
              {description && (
                <div className="text-xs text-muted-foreground mt-0.5">
                  {description}
                </div>
              )}
            </div>
            {headerActions && (
              <div className="flex items-center gap-2 shrink-0">
                {headerActions}
              </div>
            )}
          </DialogHeader>

          <div className="flex-1 overflow-y-auto p-6 min-h-0">{currentContent}</div>

          {renderedFooter && (
            <div className="border-t border-border/60 bg-muted/10 px-6 py-3.5 flex items-center justify-between">
              {renderedFooter}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
