import loaderArtwork from "@/assets/OutlineLoaderDefault.svg"

interface AnimatedLoaderProps {
  className?: string
  sizeClassName?: string
}

export function AnimatedLoader({ className, sizeClassName = "size-24" }: AnimatedLoaderProps) {
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
        className={sizeClassName}
      />
    </div>
  )
}
