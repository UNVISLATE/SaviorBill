import { useAuth } from "@/hooks/use-auth"

export function DashboardPage() {
  const { me } = useAuth()

  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold">Добро пожаловать, {me?.login}</h1>
      <p className="text-sm text-muted-foreground">
        Дашборд — сводка (заказы, доходы, активные джобы) появится здесь по мере
        подключения страниц. См. навигацию слева для доступных разделов.
      </p>
    </div>
  )
}
