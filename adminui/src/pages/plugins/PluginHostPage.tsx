import { useEffect, useRef, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { AlertCircle, Loader2, ArrowLeft } from "lucide-react"
import { Button } from "@/components/shadsnui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/shadsnui/card"
import { api } from "@/api/api"
import { useAuth } from "@/hooks/use-auth"

export function PluginHostPage() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const { me } = useAuth()
  const containerRef = useRef<HTMLDivElement>(null)

  const [mountError, setMountError] = useState<string | null>(null)
  const [isMounting, setIsMounting] = useState(true)

  // Получаем список плагинов для поиска манифеста текущего плагина
  const { data: plugins = [], isLoading: isPluginsLoading } = useQuery({
    queryKey: ["admin", "plugins"],
    queryFn: async () => {
      const res = await api.get("/v1/admin/plugins")
      return res.data
    },
  })

  const currentPlugin = plugins.find((p: any) => p.slug === slug)

  useEffect(() => {
    if (isPluginsLoading) return
    if (!currentPlugin) {
      setIsMounting(false)
      return
    }

    const adminUi = currentPlugin.admin_ui
    if (!adminUi?.entry) {
      setMountError(`Плагин '${slug}' не имеет декларации интерфейса admin_ui.entry`)
      setIsMounting(false)
      return
    }

    let isCancelled = false
    let unmountFn: (() => void) | null = null

    async function loadAndMount() {
      try {
        setIsMounting(true)
        setMountError(null)

        // URL бандла через единый префикс mediaworker (/api/media/*)
        const entryPath = adminUi.entry.replace(/^\/+/, "")
        const versionParam = currentPlugin.version ? `?v=${currentPlugin.version}` : ""
        const bundleUrl = `/api/media/plugins/${slug}/ui/${entryPath}${versionParam}`

        // Динамический импорт ESM-модуля
        const module = await import(/* @vite-ignore */ bundleUrl)

        if (isCancelled) return

        if (!containerRef.current) return

        // 1. Паттерн монтирования через функцию mount(container, context)
        if (typeof module.mount === "function") {
          unmountFn = module.mount(containerRef.current, {
            api,
            account: me,
            navigate,
            plugin: currentPlugin,
          })
        } else if (module.default) {
          // Если экспортирован React-компонент, рендерим через ReactDOM
          const ReactDOM = await import("react-dom/client")
          const React = await import("react")
          const root = ReactDOM.createRoot(containerRef.current)
          root.render(React.createElement(module.default, { api, account: me, navigate, plugin: currentPlugin }))
          unmountFn = () => root.unmount()
        } else {
          throw new Error("Модуль плагина должен экспортировать функцию 'mount' или дефолтный компонент")
        }

        setIsMounting(false)
      } catch (err: any) {
        if (!isCancelled) {
          setMountError(err.message || String(err))
          setIsMounting(false)
        }
      }
    }

    loadAndMount()

    return () => {
      isCancelled = true
      if (unmountFn) {
        try {
          unmountFn()
        } catch {}
      }
    }
  }, [slug, currentPlugin, isPluginsLoading, me, navigate])

  if (isPluginsLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-xs text-muted-foreground gap-2">
        <Loader2 className="size-4 animate-spin" /> Загрузка манифеста плагина...
      </div>
    )
  }

  if (!currentPlugin) {
    return (
      <div className="p-6 max-w-lg mx-auto text-center space-y-4">
        <AlertCircle className="size-10 text-muted-foreground mx-auto" />
        <h2 className="text-sm font-semibold">Плагин '{slug}' не найден или отключен</h2>
        <Button variant="outline" size="sm" onClick={() => navigate("/settings/plugins")}>
          <ArrowLeft className="size-3.5 mr-1" /> К списку плагинов
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {mountError && (
        <Card className="border-destructive/40 bg-destructive/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-destructive flex items-center gap-2">
              <AlertCircle className="size-4" /> Ошибка загрузки интерфейса плагина
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-destructive/90 space-y-2">
            <p>{mountError}</p>
            <Button variant="outline" size="xs" onClick={() => navigate("/settings/plugins")}>
              В настройки плагинов
            </Button>
          </CardContent>
        </Card>
      )}

      {isMounting && !mountError && (
        <div className="flex items-center justify-center py-20 text-xs text-muted-foreground gap-2">
          <Loader2 className="size-4 animate-spin text-primary" /> Монтирование микро-фронтенда {currentPlugin.name}...
        </div>
      )}

      {/* Выделенный контейнер для монтирования плагина */}
      <div ref={containerRef} className="w-full min-h-[400px]" />
    </div>
  )
}
