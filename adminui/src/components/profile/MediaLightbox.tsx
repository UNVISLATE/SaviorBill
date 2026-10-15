import { createPortal } from "react-dom"
import { useEffect, useState } from "react"
import { Check, ChevronLeft, ChevronRight, Copy, Download, Trash2, X } from "lucide-react"

import { toastSuccess } from "@/lib/toast"

export function MediaLightbox({
  onClose,
  onPrev,
  onNext,
  children,
  caption,
  mediaUrl,
  onDelete,
  actions,
}: {
  onClose: () => void
  onPrev?: () => void
  onNext?: () => void
  children: React.ReactNode
  caption?: React.ReactNode
  mediaUrl?: string | null
  onDelete?: () => void
  actions?: React.ReactNode
}) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
      else if (e.key === "ArrowLeft") onPrev?.()
      else if (e.key === "ArrowRight") onNext?.()
    }
    document.addEventListener("keydown", onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose, onPrev, onNext])

  function handleCopy() {
    if (!mediaUrl) return
    const fullUrl = mediaUrl.startsWith("http") ? mediaUrl : `${window.location.origin}${mediaUrl}`
    void navigator.clipboard.writeText(fullUrl)
    setCopied(true)
    toastSuccess("Ссылка скопирована")
    setTimeout(() => setCopied(false), 2000)
  }

  function handleDownload() {
    if (!mediaUrl) return
    const a = document.createElement("a")
    a.href = mediaUrl
    a.download = mediaUrl.split("/").pop() || "media"
    a.target = "_blank"
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/90 p-4 backdrop-blur-md duration-150 animate-in fade-in"
      onClick={onClose}
    >
      {/* 1. Кнопка закрытия — строго в верхний правый угол экрана */}
      <button
        type="button"
        onClick={onClose}
        aria-label="Закрыть"
        className="fixed top-5 right-5 z-[220] flex size-10 items-center justify-center rounded-full border border-white/15 bg-black/60 text-white shadow-2xl backdrop-blur transition hover:scale-105 hover:bg-black/85 active:scale-95"
      >
        <X className="size-5" />
      </button>

      {/* 2. Стрелки навигации — по краям экрана */}
      {onPrev && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onPrev()
          }}
          aria-label="Предыдущий файл"
          className="fixed top-1/2 left-4 z-[220] flex size-11 -translate-y-1/2 items-center justify-center rounded-full border border-white/15 bg-black/60 text-white shadow-2xl backdrop-blur transition hover:scale-105 hover:bg-black/85 active:scale-95"
        >
          <ChevronLeft className="size-6" />
        </button>
      )}

      {onNext && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onNext()
          }}
          aria-label="Следующий файл"
          className="fixed top-1/2 right-4 z-[220] flex size-11 -translate-y-1/2 items-center justify-center rounded-full border border-white/15 bg-black/60 text-white shadow-2xl backdrop-blur transition hover:scale-105 hover:bg-black/85 active:scale-95"
        >
          <ChevronRight className="size-6" />
        </button>
      )}

      {/* 3. Центр экрана — само медиа */}
      <div
        className="relative flex max-h-[80vh] max-w-full items-center justify-center"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="overflow-hidden rounded-xl shadow-2xl">{children}</div>
      </div>

      {/* 4. Плашка информации — строго внизу по центру */}
      {caption && (
        <div
          className="fixed bottom-5 left-1/2 z-[220] -translate-x-1/2 select-none rounded-full border border-white/15 bg-black/75 px-5 py-2 text-xs font-medium text-white/90 shadow-2xl backdrop-blur max-w-[80vw] truncate"
          onClick={(e) => e.stopPropagation()}
        >
          {caption}
        </div>
      )}

      {/* 5. Иконки действий — строго внизу справа */}
      {(mediaUrl || onDelete || actions) && (
        <div
          className="fixed bottom-5 right-5 z-[220] flex items-center gap-1.5 rounded-full border border-white/15 bg-black/75 p-1.5 shadow-2xl backdrop-blur"
          onClick={(e) => e.stopPropagation()}
        >
          {mediaUrl && (
            <>
              <button
                type="button"
                onClick={handleCopy}
                title="Копировать ссылку"
                aria-label="Копировать ссылку"
                className="flex size-8 items-center justify-center rounded-full text-white/80 transition hover:bg-white/20 hover:text-white"
              >
                {copied ? <Check className="size-4 text-emerald-400" /> : <Copy className="size-4" />}
              </button>
              <button
                type="button"
                onClick={handleDownload}
                title="Скачать файл"
                aria-label="Скачать файл"
                className="flex size-8 items-center justify-center rounded-full text-white/80 transition hover:bg-white/20 hover:text-white"
              >
                <Download className="size-4" />
              </button>
            </>
          )}

          {actions}

          {onDelete && (
            <button
              type="button"
              onClick={onDelete}
              title="Удалить файл"
              aria-label="Удалить файл"
              className="flex size-8 items-center justify-center rounded-full text-destructive transition hover:bg-destructive/20"
            >
              <Trash2 className="size-4" />
            </button>
          )}
        </div>
      )}
    </div>,
    document.body,
  )
}
