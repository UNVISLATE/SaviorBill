import { useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { ImageOff, Loader2, ShieldAlert, Trash2, Upload, Users } from "lucide-react"

import { api } from "@/api/api.ts"
import { uploadOwnMedia } from "@/api/media-upload.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { cn } from "@/lib/utils"
import { useAuth } from "@/hooks/use-auth"
import { useSettingsMap } from "@/hooks/use-settings-map"
import { BRANDING_UPDATED_EVENT } from "@/hooks/use-branding"
import { ThemeSettings } from "./ThemeSettings"
import { Button } from "@/components/shadsnui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/shadsnui/card"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Textarea } from "@/components/shadsnui/textarea"
import { Skeleton } from "@/components/shadsnui/skeleton"

type Scope = "admin" | "client"
type Asset = "logo" | "favicon" | "mascot" | "mascot_not_found" | "catalog_banner"

const ASSET_TAG_MAP: Record<Asset, string> = {
  logo: "logo",
  favicon: "favicon",
  mascot: "mascot",
  mascot_not_found: "mnf",
  catalog_banner: "banner",
}

const CLIENT_LINKS = [
  { key: "support_link", label: "Поддержка", placeholder: "https://t.me/support" },
  { key: "telegram_channel", label: "Telegram канал", placeholder: "https://t.me/channel" },
  { key: "telegram_chat", label: "Telegram чат", placeholder: "https://t.me/chat" },
  { key: "discord_link", label: "Discord", placeholder: "https://discord.gg/..." },
] as const

function mediaUrl(token: string | undefined | null): string | null {
  return token ? `/api/media/${token}` : null
}

/** Загрузка изображения и запись его токена в `ui.{scope}.{asset}`. */
function AssetSlot({
  scope,
  asset,
  label,
  note,
  token,
  disabled,
  onDone,
}: {
  scope: Scope
  asset: Asset
  label: string
  note: string
  token: string
  disabled?: boolean
  onDone: () => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<string | null>(null)

  const write = useMutation({
    mutationFn: async (value: string) =>
      api.put(`/v1/branding/${scope}`, { [asset]: value }),
    onSuccess: () => {
      toastSuccess(`${label} обновлён`)
      setPreview(null)
      window.dispatchEvent(new Event(BRANDING_UPDATED_EVENT))
      onDone()
    },
    onError: () => toastError(`Не удалось сохранить ${label.toLowerCase()}`),
  })

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const { token: uploaded } = await uploadOwnMedia(file, {
        tag: `${scope}${ASSET_TAG_MAP[asset]}`,
      })
      await api.put(`/v1/branding/${scope}`, { [asset]: uploaded })
    },
    onSuccess: () => {
      toastSuccess(`${label} обновлён`)
      setPreview(null)
      window.dispatchEvent(new Event(BRANDING_UPDATED_EVENT))
      onDone()
    },
    onError: (err: unknown) => {
      setPreview(null)
      toastError(
        `Не удалось загрузить ${label.toLowerCase()}`,
        err instanceof Error ? err.message : undefined,
      )
    },
  })

  const busy = upload.isPending || write.isPending
  const shown = preview ?? mediaUrl(token)

  return (
    <div className="flex items-center gap-4 rounded-lg border bg-muted/10 p-3 transition-colors hover:bg-muted/20">
      <div
        className={cn(
          "flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-lg border bg-muted/40",
          busy && "opacity-50",
        )}
      >
        {shown ? (
          <img src={shown} alt="" className="size-full object-contain" />
        ) : (
          <ImageOff className="size-5 text-muted-foreground/60" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{note}</p>
      </div>

      <div className="flex shrink-0 gap-1.5">
        <Button
          size="sm"
          variant="outline"
          disabled={busy || disabled}
          onClick={() => inputRef.current?.click()}
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
          {token ? "Заменить" : "Загрузить"}
        </Button>
        {token && !disabled && (
          <Button
            size="icon"
            variant="ghost"
            className="size-8 text-muted-foreground hover:text-destructive"
            disabled={busy || disabled}
            onClick={() => write.mutate("")}
            title="Сбросить к значению по умолчанию"
          >
            <Trash2 className="size-4" />
          </Button>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) {
            setPreview(URL.createObjectURL(file))
            upload.mutate(file)
          }
          e.target.value = ""
        }}
      />
    </div>
  )
}

/** Блок 1: Административная панель (Admin UI) */
function AdminBrandingBlock() {
  const qc = useQueryClient()
  const { can } = useAuth()
  const canEdit = can("settings.raw.edit") || can("settings.edit") || can("branding")
  const { map, isLoading } = useSettingsMap()

  const savedName = map.get("ui.admin.name") ?? ""
  const savedLoginNotice = map.get("ui.admin.login_notice") ?? ""

  const [name, setName] = useState<string | null>(null)
  const [loginNotice, setLoginNotice] = useState<string | null>(null)

  const currentName = name ?? savedName
  const currentLoginNotice = loginNotice ?? savedLoginNotice
  const isDirty = currentName !== savedName || currentLoginNotice !== savedLoginNotice

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin-settings-all"] })
    void qc.invalidateQueries({ queryKey: ["branding-admin"] })
    window.dispatchEvent(new Event(BRANDING_UPDATED_EVENT))
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      await api.put("/v1/branding/admin", {
        name: currentName,
        login_notice: currentLoginNotice.trim() || "",
      })
    },
    onSuccess: () => {
      toastSuccess("Настройки панели управления сохранены")
      setName(null)
      setLoginNotice(null)
      refresh()
    },
    onError: () => toastError("Не удалось сохранить настройки панели управления"),
  })

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Панель управления (Admin UI)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="border-border/60">
      <CardHeader className="border-b bg-muted/20 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ShieldAlert className="size-4" />
          </div>
          <div>
            <CardTitle className="text-base font-semibold">Административная панель (Admin UI)</CardTitle>
            <CardDescription className="text-xs">
              Персонализация рабочей области управления, системных заголовков, оповещений и темы.
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-6 pt-6">
        {/* Основные текстовые поля */}
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="admin-name" className="text-sm font-medium">
              Название панели
            </Label>
            <Input
              id="admin-name"
              value={currentName}
              disabled={!canEdit}
              placeholder="SaviorBill Admin"
              onChange={(e) => setName(e.target.value)}
              className="max-w-md"
            />
            <p className="text-xs text-muted-foreground">
              Отображается в заголовке вкладки браузера и шапке панели.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="admin-login-notice" className="text-sm font-medium">
              Объявление на странице входа администраторов
            </Label>
            <Textarea
              id="admin-login-notice"
              value={currentLoginNotice}
              disabled={!canEdit}
              rows={3}
              placeholder="Информационное сообщение или предупреждение при авторизации..."
              onChange={(e) => setLoginNotice(e.target.value)}
              className="max-w-2xl text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Кастомное уведомление, которое видят сотрудники при входе в панель управления. Поддерживает многострочный текст.
            </p>
          </div>
        </div>

        {/* Графические ассеты */}
        <div className="space-y-3 border-t pt-5">
          <div>
            <h4 className="text-sm font-medium">Графика и логотипы</h4>
            <p className="text-xs text-muted-foreground">
              Визуальные материалы административного интерфейса.
            </p>
          </div>
          <div className="space-y-2.5">
            <AssetSlot
              scope="admin"
              asset="logo"
              label="Логотип панели"
              note="Показывается в шапке панели и на экране входа. Рекомендуется прозрачный PNG или WebP."
              token={map.get("ui.admin.logo") ?? ""}
              disabled={!canEdit}
              onDone={refresh}
            />
            <AssetSlot
              scope="admin"
              asset="favicon"
              label="Favicon вкладки"
              note="Иконка во вкладке браузера панели. Квадратный PNG, 32×32 или 64×64."
              token={map.get("ui.admin.favicon") ?? ""}
              disabled={!canEdit}
              onDone={refresh}
            />
          </div>
        </div>

        {/* Тема оформления */}
        <div className="border-t pt-5">
          <ThemeSettings scope="admin" embedded />
        </div>
      </CardContent>

      {canEdit && isDirty && (
        <CardFooter className="justify-end gap-2 border-t bg-muted/10 py-3">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setName(null)
              setLoginNotice(null)
            }}
            disabled={saveMutation.isPending}
          >
            Отменить
          </Button>
          <Button
            size="sm"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending && <Loader2 className="mr-1.5 size-4 animate-spin" />}
            Сохранить Admin UI
          </Button>
        </CardFooter>
      )}
    </Card>
  )
}

/** Блок 2: Клиентский личный кабинет (Client UI) */
function ClientBrandingBlock() {
  const qc = useQueryClient()
  const { can } = useAuth()
  const canEdit = can("settings.raw.edit") || can("settings.edit") || can("branding")
  const { map, isLoading } = useSettingsMap()

  const savedName = map.get("ui.client.name") ?? ""
  const savedLoginNotice = map.get("ui.client.login_notice") ?? ""

  const [name, setName] = useState<string | null>(null)
  const [loginNotice, setLoginNotice] = useState<string | null>(null)

  const savedLinks: Record<string, string> = {}
  for (const l of CLIENT_LINKS) {
    savedLinks[l.key] = map.get(`ui.client.settings.${l.key}`) ?? ""
  }
  const [linksDraft, setLinksDraft] = useState<Record<string, string> | null>(null)

  const currentName = name ?? savedName
  const currentLoginNotice = loginNotice ?? savedLoginNotice
  const currentLinks = linksDraft ?? savedLinks

  const isLinksDirty = CLIENT_LINKS.some(
    (l) => (currentLinks[l.key] ?? "") !== (savedLinks[l.key] ?? ""),
  )
  const isDirty =
    currentName !== savedName ||
    currentLoginNotice !== savedLoginNotice ||
    isLinksDirty

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin-settings-all"] })
    void qc.invalidateQueries({ queryKey: ["branding-client"] })
    window.dispatchEvent(new Event(BRANDING_UPDATED_EVENT))
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      await api.put("/v1/branding/client", {
        name: currentName,
        login_notice: currentLoginNotice.trim() || "",
        settings: currentLinks,
      })
    },
    onSuccess: () => {
      toastSuccess("Настройки личного кабинета сохранены")
      setName(null)
      setLoginNotice(null)
      setLinksDraft(null)
      refresh()
    },
    onError: () => toastError("Не удалось сохранить настройки личного кабинета"),
  })

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Клиентский личный кабинет (Client UI)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="border-border/60">
      <CardHeader className="border-b bg-muted/20 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500">
            <Users className="size-4" />
          </div>
          <div>
            <CardTitle className="text-base font-semibold">Клиентский личный кабинет (Client UI)</CardTitle>
            <CardDescription className="text-xs">
              Брендирование витрины и кабинета пользователя: персонажи, баннеры, каналы поддержки и стили.
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-6 pt-6">
        {/* Основные текстовые поля */}
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="client-name" className="text-sm font-medium">
              Название сервиса / магазина
            </Label>
            <Input
              id="client-name"
              value={currentName}
              disabled={!canEdit}
              placeholder="SaviorBill Store"
              onChange={(e) => setName(e.target.value)}
              className="max-w-md"
            />
            <p className="text-xs text-muted-foreground">
              Имя вашего проекта, отображаемое клиентам в шапке, письмах и уведомлениях.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="client-login-notice" className="text-sm font-medium">
              Объявление на странице входа клиентов
            </Label>
            <Textarea
              id="client-login-notice"
              value={currentLoginNotice}
              disabled={!canEdit}
              rows={3}
              placeholder="Информационное сообщение, технические работы или приветствие для клиентов..."
              onChange={(e) => setLoginNotice(e.target.value)}
              className="max-w-2xl text-sm"
            />
            <p className="text-xs text-muted-foreground">
              Кастомное уведомление в клиентском кабинете при авторизации. Поддерживает многострочный текст.
            </p>
          </div>
        </div>

        {/* Графические ассеты витрины */}
        <div className="space-y-3 border-t pt-5">
          <div>
            <h4 className="text-sm font-medium">Графика, маскоты и баннеры</h4>
            <p className="text-xs text-muted-foreground">
              Изображения для экранов входа, ошибки 404, шапки каталога и браузера.
            </p>
          </div>
          <div className="space-y-2.5">
            <AssetSlot
              scope="client"
              asset="logo"
              label="Логотип магазина"
              note="Показывается в шапке клиентского кабинета и мобильном меню."
              token={map.get("ui.client.logo") ?? ""}
              disabled={!canEdit}
              onDone={refresh}
            />
            <AssetSlot
              scope="client"
              asset="favicon"
              label="Favicon витрины"
              note="Иконка вкладки клиентского сайта. Рекомендуется 32×32 или 64×64."
              token={map.get("ui.client.favicon") ?? ""}
              disabled={!canEdit}
              onDone={refresh}
            />
            <AssetSlot
              scope="client"
              asset="mascot"
              label="Маскот экрана входа"
              note="Персонаж на левой части страницы авторизации. Рекомендуется PNG/WebP с прозрачным фоном."
              token={map.get("ui.client.mascot") ?? ""}
              disabled={!canEdit}
              onDone={refresh}
            />
            <AssetSlot
              scope="client"
              asset="mascot_not_found"
              label="Маскот страницы 404"
              note="Иллюстрация на экране отсутствующей страницы. Рекомендуется PNG или WebP."
              token={map.get("ui.client.mascot_not_found") ?? ""}
              disabled={!canEdit}
              onDone={refresh}
            />
            <AssetSlot
              scope="client"
              asset="catalog_banner"
              label="Баннер каталога услуг"
              note="Фоновое изображение Hero-блока каталога услуг. Широкоформатный PNG/WebP/JPG."
              token={map.get("ui.client.catalog_banner") ?? ""}
              disabled={!canEdit}
              onDone={refresh}
            />
          </div>
        </div>

        {/* Ссылки сообщества и соцсетей */}
        <div className="space-y-3 border-t pt-5">
          <div>
            <h4 className="text-sm font-medium">Ссылки сообщества и поддержка</h4>
            <p className="text-xs text-muted-foreground">
              Отображаются в подвале личного кабинета, виджетах и на странице обратной связи.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {CLIENT_LINKS.map((item) => (
              <div key={item.key} className="space-y-1.5 rounded-lg border bg-muted/15 p-3">
                <Label htmlFor={`client-link-${item.key}`} className="text-xs font-medium">
                  {item.label}
                </Label>
                <Input
                  id={`client-link-${item.key}`}
                  value={currentLinks[item.key] ?? ""}
                  placeholder={item.placeholder}
                  disabled={!canEdit}
                  onChange={(e) =>
                    setLinksDraft({ ...currentLinks, [item.key]: e.target.value })
                  }
                  className="h-9 text-xs"
                />
              </div>
            ))}
          </div>
        </div>

        {/* Тема оформления */}
        <div className="border-t pt-5">
          <ThemeSettings scope="client" embedded />
        </div>
      </CardContent>

      {canEdit && isDirty && (
        <CardFooter className="justify-end gap-2 border-t bg-muted/10 py-3">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setName(null)
              setLoginNotice(null)
              setLinksDraft(null)
            }}
            disabled={saveMutation.isPending}
          >
            Отменить
          </Button>
          <Button
            size="sm"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending && <Loader2 className="mr-1.5 size-4 animate-spin" />}
            Сохранить Client UI
          </Button>
        </CardFooter>
      )}
    </Card>
  )
}

/**
 * Брендирование SaviorBill:
 * Разделено на 2 самодостаточных блока: Административная панель и Клиентский личный кабинет.
 */
export function SettingsBranding() {
  return (
    <div className="max-w-4xl space-y-8 pb-10">
      <div>
        <h2 className="text-xl font-bold tracking-tight">Брендирование и визуальное оформление</h2>
        <p className="text-sm text-muted-foreground">
          Управление внешним видом, названиями, баннерами объявлений, маскотами и палитрами для администраторов и клиентов.
        </p>
      </div>

      {/* Блок 1: Административная панель */}
      <AdminBrandingBlock />

      {/* Блок 2: Клиентский личный кабинет */}
      <ClientBrandingBlock />
    </div>
  )
}
