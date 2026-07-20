import { cn } from "@/lib/utils"

/**
 * Логотип unvi — у исходного webp заметные прозрачные поля сверху/снизу
 * (глиф занимает ~70% канвы), из-за чего в маленьких размерах (навбар,
 * логин) он визуально выглядит "сжатым". Обрезаем поля через
 * overflow-hidden + scale вместо правки самого файла.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <div className={cn("relative shrink-0 overflow-hidden", className)}>
      <img
        src="/unvi/logo_1x1_128.webp"
        alt=""
        className="absolute inset-0 size-full scale-[1.35] object-contain"
      />
    </div>
  )
}
