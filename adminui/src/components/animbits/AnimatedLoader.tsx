import loaderArtwork from "@/assets/OutlineLoaderDefault.svg"

interface AnimatedLoaderProps {
  className?: string
}

export function AnimatedLoader({ className }: AnimatedLoaderProps) {
  return (
    <div
      className={`flex items-center justify-center ${className ?? ""}`}
      role="status"
      aria-label="Загрузка"
    >
      <img
        src={loaderArtwork}
        alt=""
        aria-hidden="true"
        className="size-24"
      />
    </div>
  )
}
