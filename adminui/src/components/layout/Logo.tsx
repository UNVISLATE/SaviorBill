import { cn } from "@/lib/utils"

/**
 * Логотип — показываем целиком, без кругового кропа и масштабирования:
 * многие логотипы теряют половину содержимого, если их обрезать в круг.
 * `object-contain` без scale/overflow-hidden — весь квадрат/прямоугольник
 * всегда виден полностью, даже если у файла есть прозрачные поля.
 *
 * `src` — опциональное переопределение (см. `hooks/use-branding.ts`):
 * если в настройках `ui.admin.logo` загружен собственный логотип, панель
 * должна показывать именно его, а не захардкоженный logo unvi по умолчанию.
 */
export function Logo({ className, src }: { className?: string; src?: string | null }) {
  return (
    <div className={cn("relative shrink-0", className)}>
      <img
        src={src || "/unvi/logo_1x1_128.webp"}
        alt=""
        className="absolute inset-0 size-full object-contain"
      />
    </div>
  )
}
