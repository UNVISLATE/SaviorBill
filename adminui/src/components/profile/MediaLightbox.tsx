import { createPortal } from "react-dom"
import { useEffect } from "react"
import { ChevronLeft, ChevronRight, X } from "lucide-react"

/**
 * Полноэкранный просмотр медиа "как в мессенджерах" — отдельный элемент
 * поверх всего (portal в ``document.body``), не переиспользует диалоговый
 * шаблон (у него слишком нарядная рамка/паддинги для полноэкранного фото).
 *
 * - Клик по затемнённому фону закрывает; клик по самому изображению/подписи
 *   — не закрывает (``stopPropagation``).
 * - Крестик сидит на самом углу картинки (частично перекрывая его), а не
 *   где-то в углу экрана.
 * - На мобильных подпись лежит прямо на фото затемняющим градиентом снизу;
 *   на широких экранах — отдельной карточкой под изображением.
 */
export function MediaLightbox({
  onClose,
  onPrev,
  onNext,
  children,
  caption,
}: {
  onClose: () => void
  /** Навигация между соседними файлами галереи (§5.8) — если не задано, стрелки не показываются. */
  onPrev?: () => void
  onNext?: () => void
  children: React.ReactNode
  caption?: React.ReactNode
}) {
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

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/90 p-4 backdrop-blur-sm duration-150 animate-in fade-in sm:p-10"
      onClick={onClose}
    >
      <div
        className="relative flex max-h-full max-w-full flex-col items-center gap-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="relative max-h-[75vh] max-w-full">
          <div className="overflow-hidden rounded-lg shadow-2xl">{children}</div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="absolute -top-3 -right-3 flex size-8 items-center justify-center rounded-full border bg-popover text-foreground shadow-lg ring-1 ring-foreground/10 transition-transform hover:scale-105 active:scale-95"
          >
            <X className="size-4" />
          </button>

          {onPrev && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onPrev()
              }}
              aria-label="Предыдущий файл"
              className="absolute top-1/2 left-2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-white transition-colors hover:bg-black/70"
            >
              <ChevronLeft className="size-5" />
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
              className="absolute top-1/2 right-2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-white transition-colors hover:bg-black/70"
            >
              <ChevronRight className="size-5" />
            </button>
          )}

          {/* Мобильные: подпись прямо на фото затемнением снизу. */}
          {caption && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 rounded-b-lg bg-gradient-to-t from-black/85 to-transparent p-3 text-xs text-white sm:hidden">
              {caption}
            </div>
          )}
        </div>

        {/* Широкие экраны: подпись отдельной карточкой под изображением. */}
        {caption && (
          <div className="hidden max-w-full rounded-lg bg-popover px-4 py-2 text-xs text-muted-foreground ring-1 ring-foreground/10 sm:block">
            {caption}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}
