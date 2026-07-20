import { cn } from "@/lib/utils"

/**
 * Логотип unvi — показываем целиком, без кругового кропа и масштабирования:
 * многие логотипы теряют половину содержимого, если их обрезать в круг.
 * `object-contain` без scale/overflow-hidden — весь квадрат/прямоугольник
 * всегда виден полностью, даже если у файла есть прозрачные поля.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <div className={cn("relative shrink-0", className)}>
      <img
        src="/unvi/logo_1x1_128.webp"
        alt=""
        className="absolute inset-0 size-full object-contain"
      />
    </div>
  )
}
