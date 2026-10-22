import React from "react"
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from "@/components/shadsnui/context-menu"
import {
  Eye,
  Copy,
  Download,
  Trash2,
  UserRound,
  Tag,
  Check,
  ExternalLink,
  Pencil,
} from "lucide-react"
import { toastSuccess } from "@/lib/toast"

export interface MediaContextItemData {
  id: number
  token: string
  url: string
  kind?: string
  status?: string
  name?: string | null
  tag?: string | null
  mime?: string | null
  size?: number | null
}

export interface MediaContextMenuProps {
  children: React.ReactNode
  item: MediaContextItemData
  asChild?: boolean
  onOpenPreview?: () => void
  onRename?: () => void
  onSetAvatar?: () => void
  onDelete?: () => void
  onChangePlacement?: (placement: string) => void
  placementOptions?: { value: string; label: string }[]
  currentPlacement?: string
  canDelete?: boolean
  canSetAvatar?: boolean
}

export function MediaContextMenu({
  children,
  item,
  asChild = false,
  onOpenPreview,
  onRename,
  onSetAvatar,
  onDelete,
  onChangePlacement,
  placementOptions,
  currentPlacement,
  canDelete = true,
  canSetAvatar = false,
}: MediaContextMenuProps) {
  const fullUrl = item.url.startsWith("http") ? item.url : `${window.location.origin}${item.url}`

  const copyToClipboard = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toastSuccess(`${label} скопирован в буфер`)
    } catch {
      // Ignore
    }
  }

  const downloadFile = () => {
    const a = document.createElement("a")
    a.href = item.url
    a.download = `${item.name || item.token}${item.kind === "video" ? ".webm" : ".webp"}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  const isImage = item.kind === "image" || (item.mime && item.mime.startsWith("image/"))

  return (
    <ContextMenu>
      {asChild ? (
        <ContextMenuTrigger render={children as React.ReactElement} />
      ) : (
        <ContextMenuTrigger>{children}</ContextMenuTrigger>
      )}
      <ContextMenuContent className="w-56 text-xs">
        {onOpenPreview && (
          <ContextMenuItem
            onClick={(e) => {
              e.stopPropagation()
              onOpenPreview()
            }}
            className="gap-2 cursor-pointer"
          >
            <Eye className="size-4 text-muted-foreground" />
            <span>Открыть просмотр</span>
          </ContextMenuItem>
        )}

        {onRename && (
          <ContextMenuItem
            onClick={(e) => {
              e.stopPropagation()
              e.preventDefault()
              onRename()
            }}
            className="gap-2 cursor-pointer"
          >
            <Pencil className="size-4 text-muted-foreground" />
            <span>Переименовать</span>
          </ContextMenuItem>
        )}

        <ContextMenuItem
          onClick={() => copyToClipboard(fullUrl, "Прямой URL")}
          className="gap-2 cursor-pointer"
        >
          <Copy className="size-4 text-muted-foreground" />
          <span>Копировать прямую ссылку</span>
        </ContextMenuItem>

        <ContextMenuItem
          onClick={() => window.open(item.url, "_blank")}
          className="gap-2 cursor-pointer"
        >
          <ExternalLink className="size-4 text-muted-foreground" />
          <span>Открыть в новой вкладке</span>
        </ContextMenuItem>

        {/* Submenu for placement if provided */}
        {placementOptions && onChangePlacement && (
          <ContextMenuSub>
            <ContextMenuSubTrigger className="gap-2 cursor-pointer">
              <Tag className="size-4 text-muted-foreground" />
              <span>Назначение (Placement)</span>
            </ContextMenuSubTrigger>
            <ContextMenuSubContent className="w-44 text-xs">
              {placementOptions.map((opt) => (
                <ContextMenuItem
                  key={opt.value}
                  onClick={() => onChangePlacement(opt.value)}
                  className="gap-2 cursor-pointer justify-between"
                >
                  <span>{opt.label}</span>
                  {currentPlacement === opt.value && (
                    <Check className="size-3.5 text-primary" />
                  )}
                </ContextMenuItem>
              ))}
            </ContextMenuSubContent>
          </ContextMenuSub>
        )}

        {/* Set as avatar if available */}
        {canSetAvatar && isImage && onSetAvatar && (
          <ContextMenuItem
            onClick={(e) => {
              e.stopPropagation()
              onSetAvatar()
            }}
            className="gap-2 cursor-pointer"
          >
            <UserRound className="size-4 text-muted-foreground" />
            <span>Сделать аватаром</span>
          </ContextMenuItem>
        )}

        <ContextMenuItem
          onClick={(e) => {
            e.stopPropagation()
            downloadFile()
          }}
          className="gap-2 cursor-pointer"
        >
          <Download className="size-4 text-muted-foreground" />
          <span>Скачать файл</span>
        </ContextMenuItem>

        {canDelete && onDelete && (
          <>
            <ContextMenuSeparator />
            <ContextMenuItem
              onClick={(e) => {
                e.stopPropagation()
                onDelete()
              }}
              className="gap-2 cursor-pointer text-destructive focus:text-destructive focus:bg-destructive/10"
            >
              <Trash2 className="size-4" />
              <span>Удалить медиа</span>
            </ContextMenuItem>
          </>
        )}
      </ContextMenuContent>
    </ContextMenu>
  )
}
