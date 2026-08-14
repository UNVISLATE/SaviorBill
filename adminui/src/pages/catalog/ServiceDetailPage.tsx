import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "react-router-dom"
import { ArrowLeft, Eye, EyeOff, ImagePlus, KeyRound, Plus, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
import { Textarea } from "@/components/shadsnui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/shadsnui/tabs"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/shadsnui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"
import { MediaPickerDialog } from "@/components/media/MediaPickerDialog"
import { toastError, toastSuccess } from "@/lib/toast"

interface Catalog {
  id: number
  name: string
}

interface ServiceAdmin {
  id: number
  slug: string
  name: string
  description: string | null
  catalog_id: number | null
  price: string
  currency: string
  delivery: string
  is_active: boolean
  out_of_stock: boolean | null
  lua_script_id: number | null
  lua_script_version: number | null
  params: Record<string, unknown>
  settings: Record<string, unknown>
  warnings: string[]
}

interface LuaScript {
  id: number
  name: string
}

interface Attachment {
  id: number
  media_id: number
  token: string
  kind: string
  tag: string | null
  position: number
  url: string
}

interface ServiceKey {
  id: number
  is_used: boolean
  used_at: string | null
  order_id: number | null
  created_at: string
  value: string
}

interface Stock {
  available: number
  out_of_stock: boolean
}

function GeneralTab({ service, catalogs }: { service: ServiceAdmin; catalogs: Catalog[] | undefined }) {
  const [name, setName] = useState(service.name)
  const [description, setDescription] = useState(service.description ?? "")
  const [catalogId, setCatalogId] = useState(service.catalog_id ? String(service.catalog_id) : "")
  const [price, setPrice] = useState(service.price)
  const [currency, setCurrency] = useState(service.currency)
  const [delivery, setDelivery] = useState<"key" | "lua">(service.delivery as "key" | "lua")
  const [luaScriptId, setLuaScriptId] = useState(service.lua_script_id ? String(service.lua_script_id) : "")
  const [isActive, setIsActive] = useState(service.is_active)
  const [paramsText, setParamsText] = useState(JSON.stringify(service.params, null, 2))
  const [settingsText, setSettingsText] = useState(JSON.stringify(service.settings, null, 2))
  const [jsonError, setJsonError] = useState<string | null>(null)
  const qc = useQueryClient()

  const { data: luaScripts } = useQuery({
    queryKey: ["admin-lua-scripts-lookup"],
    queryFn: async () => (await api.get<LuaScript[]>("/v1/admin/lua")).data,
    enabled: delivery === "lua",
    staleTime: 60_000,
  })

  const save = useMutation({
    mutationFn: async () => {
      let params: unknown
      let settings: unknown
      try {
        params = JSON.parse(paramsText)
        settings = JSON.parse(settingsText)
      } catch {
        setJsonError("params/settings должны быть корректным JSON")
        throw new Error("invalid json")
      }
      setJsonError(null)
      return api.patch(`/v1/admin/services/${service.id}`, {
        name,
        description: description || null,
        catalog_id: catalogId ? Number(catalogId) : null,
        price,
        currency,
        delivery,
        lua_script_id: delivery === "lua" ? (luaScriptId ? Number(luaScriptId) : null) : null,
        params,
        settings,
        is_active: isActive,
      })
    },
    onSuccess: (res) => {
      const warnings = (res.data as ServiceAdmin).warnings
      toastSuccess("Услуга сохранена")
      warnings?.forEach((w) => toastError("Предупреждение", w))
      void qc.invalidateQueries({ queryKey: ["admin-service", service.id] })
      void qc.invalidateQueries({ queryKey: ["admin-services"] })
    },
    onError: (e: unknown) => {
      if ((e as Error).message !== "invalid json") toastError("Не удалось сохранить услугу", getErrorDetail(e))
    },
  })

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Основное</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <Label>Название</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Описание</Label>
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
          </div>
          <div className="space-y-1">
            <Label>Каталог</Label>
            <Select value={catalogId || "root"} onValueChange={(v) => setCatalogId(v === "root" ? "" : v ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder="Без каталога" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="root">— Без каталога —</SelectItem>
                {catalogs?.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Цена</Label>
              <Input type="number" min={0} step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Валюта</Label>
              <Input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={8} />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <Label>Активна</Label>
            <Switch checked={isActive} onCheckedChange={setIsActive} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Выдача</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <Label>Способ выдачи</Label>
            <Select value={delivery} onValueChange={(v) => setDelivery((v as "key" | "lua") ?? "key")}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="key">Ключи из пула</SelectItem>
                <SelectItem value="lua">Lua-скрипт</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {delivery === "lua" && (
            <div className="space-y-1">
              <Label>Скрипт</Label>
              <Select value={luaScriptId} onValueChange={(v) => setLuaScriptId(v ?? "")}>
                <SelectTrigger>
                  <SelectValue placeholder="Выберите скрипт" />
                </SelectTrigger>
                <SelectContent>
                  {luaScripts?.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-1">
            <Label>Params (JSON)</Label>
            <Textarea
              className="font-mono text-xs"
              rows={5}
              value={paramsText}
              onChange={(e) => setParamsText(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label>Settings (JSON, доступно скрипту как service.settings.*)</Label>
            <Textarea
              className="font-mono text-xs"
              rows={5}
              value={settingsText}
              onChange={(e) => setSettingsText(e.target.value)}
            />
          </div>
          {jsonError && <p className="text-xs text-destructive">{jsonError}</p>}
        </CardContent>
      </Card>

      <div className="lg:col-span-2">
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          Сохранить
        </Button>
      </div>
    </div>
  )
}

function AttachmentsTab({ serviceId }: { serviceId: number }) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["admin-service-attachments", serviceId],
    queryFn: async () => (await api.get<Attachment[]>(`/v1/admin/services/${serviceId}/attachments`)).data,
  })

  const add = useMutation({
    mutationFn: async (mediaId: number) =>
      api.post(`/v1/admin/services/${serviceId}/attachments`, { media_id: mediaId, position: data?.length ?? 0 }),
    onSuccess: () => {
      toastSuccess("Вложение добавлено")
      void qc.invalidateQueries({ queryKey: ["admin-service-attachments", serviceId] })
    },
    onError: (e: unknown) => toastError("Не удалось добавить вложение", getErrorDetail(e)),
  })

  const remove = useMutation({
    mutationFn: async (attId: number) => api.delete(`/v1/admin/services/${serviceId}/attachments/${attId}`),
    onSuccess: () => {
      toastSuccess("Вложение удалено")
      void qc.invalidateQueries({ queryKey: ["admin-service-attachments", serviceId] })
    },
    onError: (e: unknown) => toastError("Не удалось удалить вложение", getErrorDetail(e)),
  })

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Вложения (изображения/видео карточки услуги)</CardTitle>
        <Button size="sm" onClick={() => setPickerOpen(true)}>
          <ImagePlus className="size-4" /> Добавить
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
        {!isLoading && (data?.length ?? 0) === 0 && (
          <p className="text-sm text-muted-foreground">Вложений пока нет.</p>
        )}
        {!isLoading && (data?.length ?? 0) > 0 && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {data!.map((a) => (
              <div key={a.id} className="group relative overflow-hidden rounded-md border">
                {a.kind === "image" ? (
                  <img src={a.url} alt={a.tag ?? ""} className="aspect-square w-full object-cover" />
                ) : (
                  <div className="flex aspect-square w-full items-center justify-center bg-muted text-xs text-muted-foreground">
                    {a.kind}
                  </div>
                )}
                <Button
                  variant="destructive"
                  size="icon"
                  className="absolute right-1 top-1 size-6 opacity-0 transition-opacity group-hover:opacity-100"
                  onClick={() => remove.mutate(a.id)}
                >
                  <Trash2 className="size-3" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
      <MediaPickerDialog open={pickerOpen} onOpenChange={setPickerOpen} onSelect={(m) => add.mutate(m.id)} />
    </Card>
  )
}

function KeysTab({ serviceId }: { serviceId: number }) {
  const { can } = useAuth()
  const canReveal = can("ownersec.servicekeys.read")
  const [importText, setImportText] = useState("")
  const [revealed, setRevealed] = useState<Record<number, string>>({})
  const qc = useQueryClient()

  const { data: stock } = useQuery({
    queryKey: ["admin-service-stock", serviceId],
    queryFn: async () => (await api.get<Stock>(`/v1/admin/services/${serviceId}/keys/stock`)).data,
  })

  const { data: keys, isLoading } = useQuery({
    queryKey: ["admin-service-keys", serviceId],
    queryFn: async () =>
      (
        await api.get<{ items: ServiceKey[] }>(`/v1/admin/services/${serviceId}/keys`, {
          params: { limit: 100, sort: "-created_at" },
        })
      ).data.items,
  })

  const importKeys = useMutation({
    mutationFn: async () => {
      const values = importText.split("\n").map((v) => v.trim()).filter(Boolean)
      return api.post(`/v1/admin/services/${serviceId}/keys/import`, { values })
    },
    onSuccess: (res) => {
      const body = res.data as { added: number; skipped: number }
      toastSuccess(`Импортировано: ${body.added}${body.skipped ? `, пропущено дублей: ${body.skipped}` : ""}`)
      setImportText("")
      void qc.invalidateQueries({ queryKey: ["admin-service-keys", serviceId] })
      void qc.invalidateQueries({ queryKey: ["admin-service-stock", serviceId] })
    },
    onError: (e: unknown) => toastError("Не удалось импортировать ключи", getErrorDetail(e)),
  })

  const removeKey = useMutation({
    mutationFn: async (keyId: number) => api.delete(`/v1/admin/services/${serviceId}/keys/${keyId}`),
    onSuccess: () => {
      toastSuccess("Ключ удалён")
      void qc.invalidateQueries({ queryKey: ["admin-service-keys", serviceId] })
      void qc.invalidateQueries({ queryKey: ["admin-service-stock", serviceId] })
    },
    onError: (e: unknown) => toastError("Не удалось удалить ключ", getErrorDetail(e)),
  })

  const reveal = async (keyId: number) => {
    if (revealed[keyId]) {
      setRevealed((prev) => { const next = { ...prev }; delete next[keyId]; return next })
      return
    }
    try {
      const res = await api.get<{ value: string }>(`/v1/admin/services/${serviceId}/keys/${keyId}/reveal`)
      setRevealed((prev) => ({ ...prev, [keyId]: res.data.value }))
    } catch (e) {
      toastError("Не удалось раскрыть ключ", getErrorDetail(e))
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Card size="sm">
          <CardContent className="py-4">
            <p className="text-xs text-muted-foreground">Доступно</p>
            <p className="text-2xl font-semibold tabular-nums">{stock?.available ?? "—"}</p>
          </CardContent>
        </Card>
        <Card size="sm" className="sm:col-span-2">
          <CardContent className="py-4">
            {stock?.out_of_stock ? (
              <Badge variant="destructive">Ключи закончились — импортируйте новые</Badge>
            ) : (
              <Badge variant="outline">Ключей достаточно</Badge>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Импорт ключей</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Textarea
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder={"По одному ключу на строку\nKEY-AAAA-1111\nKEY-BBBB-2222"}
            rows={5}
            className="font-mono text-xs"
          />
          <Button
            size="sm"
            disabled={!importText.trim() || importKeys.isPending}
            onClick={() => importKeys.mutate()}
          >
            <Plus className="size-4" /> Импортировать
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Ключи в пуле</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
          {!isLoading && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Значение</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead>Создан</TableHead>
                  <TableHead className="text-right">Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(keys?.length ?? 0) === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="py-6 text-center text-sm text-muted-foreground">
                      Пул ключей пуст
                    </TableCell>
                  </TableRow>
                )}
                {keys?.map((k) => (
                  <TableRow key={k.id}>
                    <TableCell className="font-mono text-xs">
                      {revealed[k.id] ?? "•".repeat(12)}
                    </TableCell>
                    <TableCell>
                      {k.is_used ? <Badge variant="outline">использован</Badge> : <Badge>свободен</Badge>}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(k.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="flex justify-end gap-1">
                      {canReveal && (
                        <Button variant="ghost" size="icon" className="size-8" onClick={() => reveal(k.id)}>
                          {revealed[k.id] ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                        </Button>
                      )}
                      {!k.is_used && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-8 text-destructive"
                          onClick={() => removeKey.mutate(k.id)}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export function ServiceDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const serviceId = Number(id)

  const { data: service, isLoading } = useQuery({
    queryKey: ["admin-service", serviceId],
    queryFn: async () => (await api.get<ServiceAdmin>(`/v1/admin/services/${serviceId}`)).data,
    enabled: Number.isFinite(serviceId),
  })

  const { data: catalogs } = useQuery({
    queryKey: ["admin-catalogs"],
    queryFn: async () => (await api.get<Catalog[]>("/v1/admin/catalogs")).data,
    staleTime: 60_000,
  })

  if (isLoading || !service) {
    return <p className="text-sm text-muted-foreground">Загрузка…</p>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" className="size-8" onClick={() => navigate("/services")}>
          <ArrowLeft className="size-4" />
        </Button>
        <h1 className="text-xl font-semibold">{service.name}</h1>
        <span className="font-mono text-xs text-muted-foreground">{service.slug}</span>
      </div>

      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">Основное</TabsTrigger>
          <TabsTrigger value="attachments">Вложения</TabsTrigger>
          {service.delivery === "key" && (
            <TabsTrigger value="keys">
              <KeyRound className="size-3.5" /> Ключи
            </TabsTrigger>
          )}
        </TabsList>
        <TabsContent value="general">
          <GeneralTab service={service} catalogs={catalogs} />
        </TabsContent>
        <TabsContent value="attachments">
          <AttachmentsTab serviceId={service.id} />
        </TabsContent>
        {service.delivery === "key" && (
          <TabsContent value="keys">
            <KeysTab serviceId={service.id} />
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}
