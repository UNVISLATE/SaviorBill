import { Link } from "react-router-dom"
import { Home, MoveLeft } from "lucide-react"

import { Button } from "@/components/shadsnui/button"

export function NotFoundPage() {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center p-6 text-center select-none bg-background">
      <div className="flex max-w-md flex-col items-center gap-6">
        <div className="relative">
          <div
            className="absolute -inset-4 rounded-full bg-primary/10 blur-2xl pointer-events-none"
            aria-hidden
          />
          <img
            src="/unvi/mascot/NotFoundMascotUNVI.webp"
            alt="Страница не найдена"
            className="relative size-56 object-contain drop-shadow-md transition-transform hover:scale-105 duration-300"
          />
        </div>

        <div className="space-y-2">
          <span className="inline-block rounded-full border border-border/80 bg-muted/60 px-3 py-1 font-mono text-xs font-semibold text-muted-foreground">
            Ошибка 404
          </span>
          <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Страница не найдена
          </h1>
          <p className="text-sm text-muted-foreground">
            Запрашиваемый раздел панели управления SaviorBill перемещён, удалён или никогда не существовал.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => window.history.back()}>
            <MoveLeft className="size-4" /> Назад
          </Button>
          <Link to="/">
            <Button size="sm" className="gap-2">
              <Home className="size-4" /> На главную
            </Button>
          </Link>
        </div>
      </div>
    </div>
  )
}

export default NotFoundPage
