import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Plug,
  RefreshCw,
  Database,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  SlidersHorizontal,
  ExternalLink,
  MessageSquare,
  Gift,
  Users,
  Shield,
  Layers,
} from "lucide-react"
import { Button } from "@/components/shadsnui/button"
import { Badge } from "@/components/shadsnui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/shadsnui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import { DeclarativeForm } from "@/components/common/forms/DeclarativeForm"
import { api } from "@/api/api"
import { toast } from "sonner"

interface PluginInfo {
  slug: str
  name: string
  version: string
  description: string
  icon: string
  author: string
  status: "active" | "disabled" | "error" | "orphaned"
  error: string | null
  permissions: Array<{ key: string; name: string; description?: string }>
  has_settings: boolean
  admin_ui?: {
    entry: string
    nav?: {
      title: string
      icon: string
      category: string
      order: number
      required_perm?: string
    }
  }
  client_embed?: {
    widget_script: string
    custom_element: string
  }
  db_size: {
    bytes: number
    pretty: string
  }
}

type str = string

const ICON_MAP: Record<string, React.ElementType> = {
  Plug,
  MessageSquare,
  Gift,
  Users,
  Shield,
  Database,
  Layers,
}

export function PluginsSettingsPage() {
  const queryClient = useQueryClient()
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null)
  const [dropTargetSlug, setDropTargetSlug] = useState<string | null>(null)

  // 1. Загрузка списка плагинов
  const { data: plugins = [], isLoading } = useQuery<PluginInfo[]>({
    queryKey: ["admin", "plugins"],
    queryFn: async () => {
      const res = await api.get("/v1/admin/plugins")
      return res.data
    },
  })

  // 2. Горячая перезагрузка плагинов
  const reindexMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post("/v1/admin/plugins/reindex")
      return res.data
    },
    onSuccess: (data) => {
      toast.success(`Плагины перезагружены (активно: ${data.loaded_count})`)
      queryClient.invalidateQueries({ queryKey: ["admin", "plugins"] })
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || "Ошибка пересканирования плагинов")
    },
  })

  // 3. Полное удаление схемы данных плагина (DROP SCHEMA)
  const dropDataMutation = useMutation({
    mutationFn: async (slug: string) => {
      const res = await api.delete(`/v1/admin/plugins/${slug}/data`)
      return res.data
    },
    onSuccess: (_, slug) => {
      toast.success(`Данные плагина '${slug}' удалены из БД`)
      if (selectedSlug === slug) setSelectedSlug(null)
      setDropTargetSlug(null)
      queryClient.invalidateQueries({ queryKey: ["admin", "plugins"] })
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || "Ошибка удаления данных")
    },
  })

  // Текущий выбранный плагин
  const activePlugin = plugins.find((p) => p.slug === selectedSlug)

  return (
    <div className="space-y-6">
      {/* Шапка страницы */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Плагины ядра</h2>
          <p className="text-xs text-muted-foreground">
            Расширения SaviorBill с изолированными схемами PostgreSQL, фоновыми задачами и UI-микробандлами
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => reindexMutation.mutate()}
            disabled={reindexMutation.isPending}
            className="cursor-pointer gap-2"
          >
            <RefreshCw className={`size-3.5 ${reindexMutation.isPending ? "animate-spin" : ""}`} />
            Пересканировать
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="py-12 text-center text-xs text-muted-foreground">
          Загрузка установленных плагинов...
        </div>
      ) : plugins.length === 0 ? (
        <Card className="border-border/60 bg-card/60">
          <CardContent className="py-12 text-center space-y-3">
            <div className="mx-auto flex size-12 items-center justify-center rounded-xl border border-border/80 bg-muted/40">
              <Plug className="size-6 text-muted-foreground" />
            </div>
            <div className="space-y-1">
              <h3 className="text-sm font-medium">Нет установленных плагинов</h3>
              <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                Поместите папку с плагином и файлом <code>manifest.json</code> в каталог{" "}
                <code>./data/plugins/</code> и нажмите «Пересканировать».
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Список плагинов слева */}
          <div className="lg:col-span-5 space-y-3">
            {plugins.map((plugin) => {
              const IconComp = ICON_MAP[plugin.icon] || Plug
              const isSelected = selectedSlug === plugin.slug

              return (
                <div
                  key={plugin.slug}
                  onClick={() => {
                    if (plugin.status !== "orphaned" && plugin.has_settings) {
                      setSelectedSlug(plugin.slug)
                    }
                  }}
                  className={`group relative rounded-xl border p-4 transition-all ${
                    isSelected
                      ? "border-primary/60 bg-primary/5 shadow-2xs"
                      : "border-border/60 bg-card/40 hover:border-border hover:bg-card/70"
                  } ${
                    plugin.has_settings && plugin.status !== "orphaned" ? "cursor-pointer" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-background/80 text-foreground">
                        <IconComp className="size-4 text-primary" />
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-foreground">
                            {plugin.name}
                          </span>
                          {plugin.version && (
                            <Badge variant="outline" className="text-[10px] py-0 px-1.5 h-4">
                              v{plugin.version}
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground line-clamp-2">
                          {plugin.description || "Без описания"}
                        </p>
                      </div>
                    </div>

                    {/* Статус бейдж */}
                    <div className="shrink-0">
                      {plugin.status === "active" && (
                        <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-[10px] gap-1">
                          <CheckCircle2 className="size-3" /> Активен
                        </Badge>
                      )}
                      {plugin.status === "error" && (
                        <Badge variant="destructive" className="text-[10px] gap-1">
                          <XCircle className="size-3" /> Ошибка
                        </Badge>
                      )}
                      {plugin.status === "orphaned" && (
                        <Badge variant="outline" className="text-amber-400 border-amber-500/40 text-[10px] gap-1">
                          <Database className="size-3" /> Архив БД
                        </Badge>
                      )}
                    </div>
                  </div>

                  {/* Ошибка если есть */}
                  {plugin.error && (
                    <div className="mt-2.5 rounded-lg border border-destructive/30 bg-destructive/10 p-2 text-[11px] text-destructive">
                      {plugin.error}
                    </div>
                  )}

                  {/* Метаданные футера карточки */}
                  <div className="mt-3.5 pt-3 border-t border-border/40 flex items-center justify-between text-[11px] text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <span className="flex items-center gap-1 font-mono">
                        <Database className="size-3" />
                        {plugin.db_size.pretty}
                      </span>
                      {plugin.author && (
                        <>
                          <span>•</span>
                          <span>{plugin.author}</span>
                        </>
                      )}
                    </div>

                    <div className="flex items-center gap-1.5">
                      {plugin.admin_ui?.nav && plugin.status === "active" && (
                        <a
                          href={`/plugins/${plugin.slug}`}
                          onClick={(e) => e.stopPropagation()}
                          className="flex items-center gap-1 text-[11px] text-primary hover:underline"
                        >
                          Открыть <ExternalLink className="size-3" />
                        </a>
                      )}

                      {plugin.status === "orphaned" && (
                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={(e) => {
                            e.stopPropagation()
                            setDropTargetSlug(plugin.slug)
                          }}
                          className="text-destructive hover:bg-destructive/15 text-[11px] h-6 px-2 cursor-pointer"
                        >
                          <Trash2 className="size-3 mr-1" /> Удалить БД
                        </Button>
                      )}

                      {plugin.has_settings && plugin.status !== "orphaned" && (
                        <span className="text-[11px] text-muted-foreground group-hover:text-foreground">
                          {isSelected ? "Редактирование →" : "Настройки"}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Панель настроек плагина справа */}
          <div className="lg:col-span-7">
            {activePlugin && activePlugin.has_settings ? (
              <PluginSettingsFormCard slug={activePlugin.slug} name={activePlugin.name} />
            ) : (
              <Card className="border-border/60 bg-card/30 border-dashed">
                <CardContent className="py-16 text-center text-xs text-muted-foreground space-y-2">
                  <SlidersHorizontal className="size-8 mx-auto text-muted-foreground/60" />
                  <p>Выберите плагин из списка слева для редактирования его параметров</p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* Диалог подтверждения удаления схемы данных из БД */}
      <Dialog open={Boolean(dropTargetSlug)} onOpenChange={(open) => !open && setDropTargetSlug(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="size-5" /> Удаление данных плагина
            </DialogTitle>
            <DialogDescription className="space-y-2 pt-2 text-xs">
              <p>
                Вы уверены, что хотите удалить схему <code>plugin_{dropTargetSlug}</code> и все
                сохранённые параметры плагина из базы данных?
              </p>
              <p className="font-semibold text-destructive">
                Это действие необратимо. Все таблицы, записи и настройки этого плагина будут
                безвозвратно удалены (DROP SCHEMA CASCADE).
              </p>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => setDropTargetSlug(null)}>
              Отмена
            </Button>
            <Button
              variant="destructive"
              onClick={() => dropTargetSlug && dropDataMutation.mutate(dropTargetSlug)}
              disabled={dropDataMutation.isPending}
              className="cursor-pointer"
            >
              {dropDataMutation.isPending ? "Удаление..." : "Удалить данные из БД"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function PluginSettingsFormCard({ slug, name }: { slug: string; name: string }) {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["admin", "plugin-settings", slug],
    queryFn: async () => {
      const res = await api.get(`/v1/admin/plugins/${slug}/settings`)
      return res.data
    },
  })

  const [formValues, setFormValues] = useState<Record<string, unknown>>({})
  const [isDirty, setIsDirty] = useState(false)

  // Синхронизация при загрузке значений
  useState(() => {
    if (data?.values) {
      setFormValues(data.values)
    }
  })

  const saveMutation = useMutation({
    mutationFn: async (updated: Record<string, unknown>) => {
      const res = await api.patch(`/v1/admin/plugins/${slug}/settings`, {
        settings: updated,
      })
      return res.data
    },
    onSuccess: () => {
      toast.success(`Настройки плагина '${name}' сохранены`)
      setIsDirty(false)
      queryClient.invalidateQueries({ queryKey: ["admin", "plugin-settings", slug] })
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || "Ошибка сохранения настроек")
    },
  })

  if (isLoading) {
    return (
      <Card className="border-border/60 bg-card/60">
        <CardContent className="py-12 text-center text-xs text-muted-foreground">
          Загрузка настроек плагина...
        </CardContent>
      </Card>
    )
  }

  const schema = data?.settings_schema
  const currentValues = isDirty ? formValues : data?.values || {}

  return (
    <Card className="border-border/60 bg-card/60">
      <CardHeader className="pb-4">
        <CardTitle className="text-base flex items-center justify-between">
          <span>Настройки: {name}</span>
          <Badge variant="outline" className="font-mono text-xs">
            {slug}
          </Badge>
        </CardTitle>
        {schema?.description && (
          <CardDescription className="text-xs">{schema.description}</CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-6">
        <DeclarativeForm
          schema={schema}
          value={currentValues}
          onChange={(newVal) => {
            setFormValues(newVal)
            setIsDirty(true)
          }}
        />

        <div className="pt-4 border-t border-border/40 flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setFormValues(data?.values || {})
              setIsDirty(false)
            }}
            disabled={!isDirty || saveMutation.isPending}
          >
            Сбросить
          </Button>
          <Button
            size="sm"
            onClick={() => saveMutation.mutate(formValues)}
            disabled={!isDirty || saveMutation.isPending}
            className="cursor-pointer"
          >
            {saveMutation.isPending ? "Сохранение..." : "Сохранить параметры"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
