import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Code2,
  Info,
  Key,
  Loader2,
  RotateCcw,
  Send,
  Server,
  Shield,
  Trash2,
  XCircle,
} from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { useAuth } from "@/hooks/use-auth"
import { Badge } from "@/components/shadsnui/badge"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/shadsnui/alert-dialog"
import { LuaScriptSelect } from "@/components/common/LuaScriptSelect"

interface SmtpData {
  driver: "smtp" | "lua"
  lua_script_id: number | null
  lua_script_version: string | null
  host: string | null
  port: number
  user: string | null
  has_password: boolean
  from_email: string | null
  from_name: string | null
  encryption: "starttls" | "ssl" | "none"
  timeout: number
  configured: boolean
}

export function SmtpSettings() {
  const { me, can } = useAuth()
  const canEdit = can("settings.raw.edit") || can("settings.edit") || can("smtp.edit")
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["admin-settings-smtp"],
    queryFn: async () => (await api.get<SmtpData>("/v1/admin/settings/smtp")).data,
  })

  const [driver, setDriver] = useState<"smtp" | "lua">("smtp")
  const [luaScriptId, setLuaScriptId] = useState<string>("")
  const [luaScriptVersion, setLuaScriptVersion] = useState<string>("")

  const [host, setHost] = useState("")
  const [port, setPort] = useState(587)
  const [encryption, setEncryption] = useState<"starttls" | "ssl" | "none">("starttls")
  const [timeoutSec, setTimeoutSec] = useState(10)
  const [user, setUser] = useState("")
  const [password, setPassword] = useState("")
  const [clearPassword, setClearPassword] = useState(false)
  const [fromEmail, setFromEmail] = useState("")
  const [fromName, setFromName] = useState("")

  const [testEmail, setTestEmail] = useState("")
  const [testFromEmail, setTestFromEmail] = useState("")
  const [testFromName, setTestFromName] = useState("")
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [isResetDialogOpen, setIsResetDialogOpen] = useState(false)

  useEffect(() => {
    if (data) {
      setDriver(data.driver || "smtp")
      setLuaScriptId(data.lua_script_id ? String(data.lua_script_id) : "")
      setLuaScriptVersion(data.lua_script_version || "")
      setHost(data.host || "")
      setPort(data.port || 587)
      setEncryption(data.encryption || "starttls")
      setTimeoutSec(data.timeout || 10)
      setUser(data.user || "")
      setPassword("")
      setClearPassword(false)
      setFromEmail(data.from_email || "")
      setFromName(data.from_name || "")
    }
  }, [data])

  useEffect(() => {
    if (me?.email && !testEmail) {
      setTestEmail(me.email)
    }
  }, [me?.email, testEmail])

  // Загрузка реальных доступных версий выбранного скрипта
  const { data: scriptVersions = [] } = useQuery({
    queryKey: ["admin-lua-script-versions", luaScriptId],
    queryFn: async () => {
      if (!luaScriptId) return []
      const res = await api.get<{ version: string; is_active: boolean }[]>(
        `/v1/admin/lua/scripts/${luaScriptId}/versions`,
      )
      return res.data || []
    },
    enabled: Boolean(luaScriptId),
  })

  const saveMutation = useMutation({
    mutationFn: async () => {
      await api.post("/v1/admin/settings/smtp", {
        driver,
        lua_script_id: driver === "lua" && luaScriptId ? Number(luaScriptId) : null,
        lua_script_version: driver === "lua" && luaScriptVersion ? luaScriptVersion.trim() : null,
        host: host.trim() || null,
        port: Number(port) || 587,
        encryption,
        timeout: Number(timeoutSec) || 10,
        user: user.trim() || null,
        password: password || undefined,
        clear_password: clearPassword,
        from_email: fromEmail.trim() || null,
        from_name: fromName.trim() || null,
      })
    },
    onSuccess: () => {
      toastSuccess("Настройки почтового транспорта успешно сохранены")
      setPassword("")
      setClearPassword(false)
      void qc.invalidateQueries({ queryKey: ["admin-settings-smtp"] })
    },
    onError: (e) => toastError("Не удалось сохранить настройки", getErrorDetail(e)),
  })

  const resetMutation = useMutation({
    mutationFn: async () => {
      await api.delete("/v1/admin/settings/smtp")
    },
    onSuccess: () => {
      toastSuccess("Настройки почтового транспорта очищены")
      setDriver("smtp")
      setLuaScriptId("")
      setLuaScriptVersion("")
      setHost("")
      setPort(587)
      setEncryption("starttls")
      setTimeoutSec(10)
      setUser("")
      setPassword("")
      setClearPassword(false)
      setFromEmail("")
      setFromName("")
      setIsResetDialogOpen(false)
      void qc.invalidateQueries({ queryKey: ["admin-settings-smtp"] })
    },
    onError: (e) => toastError("Не удалось сбросить настройки", getErrorDetail(e)),
  })

  const testMutation = useMutation({
    mutationFn: async () => {
      return (
        await api.post<{ ok: boolean; message: string }>("/v1/admin/settings/smtp/test", {
          to_email: testEmail.trim(),
          from_email: testFromEmail.trim() || undefined,
          from_name: testFromName.trim() || undefined,
        })
      ).data
    },
    onSuccess: (res) => {
      setTestResult({ ok: true, message: res.message })
      toastSuccess("Тестовое письмо отправлено")
    },
    onError: (e) => {
      const err = getErrorDetail(e) || "Ошибка отправки"
      setTestResult({ ok: false, message: err })
      toastError("Ошибка отправки тестового письма", err)
    },
  })

  if (isLoading) {
    return (
      <Card className="bg-card/70 border-border/80">
        <CardContent className="p-12 text-center text-sm text-muted-foreground flex items-center justify-center gap-2">
          <Loader2 className="size-4 animate-spin" /> Загрузка настроек почты…
        </CardContent>
      </Card>
    )
  }

  const isConfigured = Boolean(data?.configured)

  return (
    <div className="space-y-6">
      {/* Карточка 1: Конфигурация транспорта */}
      <Card className="bg-card/70 border-border/80 shadow-2xs">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Server className="size-4 text-primary" /> Почтовый транспорт (Email Delivery)
              </CardTitle>
              <CardDescription className="text-xs">
                Выберите транспорт для отправки системных писем, кодов подтверждения и чеков клиентам: встроенный SMTP или Lua-скрипт API-провайдера.
              </CardDescription>
            </div>
            {isConfigured ? (
              <Badge variant="outline" className="border-emerald-500/40 text-emerald-500 bg-emerald-500/10 gap-1 text-[11px]">
                <CheckCircle2 className="size-3.5" /> Настроен
              </Badge>
            ) : (
              <Badge variant="outline" className="border-amber-500/40 text-amber-500 bg-amber-500/10 gap-1 text-[11px]">
                <XCircle className="size-3.5" /> Не настроен
              </Badge>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-5">
          {/* Выбор драйвера */}
          <div className="flex items-center gap-2 border-b border-border/60 pb-3">
            <button
              type="button"
              disabled={!canEdit}
              onClick={() => setDriver("smtp")}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${!canEdit ? "opacity-60 cursor-not-allowed" : "cursor-pointer"} ${
                driver === "smtp"
                  ? "bg-primary text-primary-foreground shadow-xs"
                  : "text-muted-foreground hover:bg-muted"
              }`}
            >
              Встроенный SMTP
            </button>
            <button
              type="button"
              disabled={!canEdit}
              onClick={() => setDriver("lua")}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 ${!canEdit ? "opacity-60 cursor-not-allowed" : "cursor-pointer"} ${
                driver === "lua"
                  ? "bg-primary text-primary-foreground shadow-xs"
                  : "text-muted-foreground hover:bg-muted"
              }`}
            >
              <Code2 className="size-3.5" /> Lua-скрипт (API-провайдер)
            </button>
          </div>

          {/* Режим Lua-драйвера */}
          {driver === "lua" ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2.5 rounded-lg border border-sky-500/20 bg-sky-500/5 px-3 py-2 text-xs text-muted-foreground">
                <Info className="size-4 text-sky-400 shrink-0" />
                <span>Подключение почтового провайдера через внешний HTTP REST API с помощью Lua-скрипта.</span>
              </div>

              <div className="grid gap-4 sm:grid-cols-12">
                <div className={`space-y-1.5 ${luaScriptId ? "sm:col-span-6" : "sm:col-span-12"}`}>
                  <Label>Выберите Lua-скрипт транспорта *</Label>
                  <LuaScriptSelect
                    kind={["email", "generic"]}
                    value={luaScriptId}
                    onChange={(id) => {
                      setLuaScriptId(id || "")
                      setLuaScriptVersion("")
                    }}
                    placeholder="Выберите скрипт почтового транспорта…"
                  />
                  <span className="text-[10px] text-muted-foreground">Скрипты вида «email» или «generic»</span>
                </div>

                {luaScriptId && (
                  <div className="space-y-1.5 sm:col-span-6">
                    <Label htmlFor="lua-script-ver">Версия скрипта</Label>
                    <Select
                      value={luaScriptVersion || "__latest__"}
                      onValueChange={(val) => setLuaScriptVersion(val === "__latest__" || !val ? "" : val)}
                    >
                      <SelectTrigger id="lua-script-ver" className="w-full">
                        <SelectValue placeholder="Последняя активная" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__latest__">Последняя активная версия (по умолчанию)</SelectItem>
                        {scriptVersions.map((v) => (
                          <SelectItem key={v.version} value={v.version}>
                            {v.version} {v.is_active ? " (активная)" : ""}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <span className="text-[10px] text-muted-foreground">
                      {scriptVersions.length === 0
                        ? "Загрузка доступных версий…"
                        : `Доступно версий: ${scriptVersions.length}`}
                    </span>
                  </div>
                )}
              </div>
            </div>
          ) : (
            /* Режим SMTP */
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-12">
                <div className="space-y-1.5 sm:col-span-6">
                  <Label htmlFor="smtp-host">Хост сервера (SMTP Host) *</Label>
                  <Input
                    id="smtp-host"
                    placeholder="smtp.bz, smtp.mailgun.org, smtp.yandex.ru"
                    value={host}
                    onChange={(e) => setHost(e.target.value)}
                  />
                </div>

                <div className="space-y-1.5 sm:col-span-2">
                  <Label htmlFor="smtp-port">Порт *</Label>
                  <Input
                    id="smtp-port"
                    type="number"
                    min={1}
                    max={65535}
                    placeholder="587"
                    value={port}
                    onChange={(e) => setPort(Number(e.target.value))}
                  />
                </div>

                <div className="space-y-1.5 sm:col-span-2">
                  <Label htmlFor="smtp-encryption" className="flex items-center gap-1">
                    <Shield className="size-3 text-primary" /> Шифрование *
                  </Label>
                  <Select
                    value={encryption}
                    onValueChange={(val) => setEncryption(val as "starttls" | "ssl" | "none")}
                  >
                    <SelectTrigger id="smtp-encryption" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="starttls">STARTTLS</SelectItem>
                      <SelectItem value="ssl">SSL / TLS</SelectItem>
                      <SelectItem value="none">Без шифрования</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5 sm:col-span-2">
                  <Label htmlFor="smtp-timeout" className="flex items-center gap-1">
                    <Clock className="size-3 text-muted-foreground" /> Таймаут (сек)
                  </Label>
                  <Input
                    id="smtp-timeout"
                    type="number"
                    min={1}
                    max={120}
                    placeholder="10"
                    value={timeoutSec}
                    onChange={(e) => setTimeoutSec(Number(e.target.value))}
                  />
                </div>
              </div>

              {/* Аутентификация SMTP */}
              <div className="grid gap-4 sm:grid-cols-12 pt-2 border-t border-border/60">
                <div className="space-y-1.5 sm:col-span-6">
                  <Label htmlFor="smtp-user">Логин / Пользователь</Label>
                  <Input
                    id="smtp-user"
                    placeholder="user@example.com или API-логин"
                    value={user}
                    onChange={(e) => setUser(e.target.value)}
                  />
                </div>

                <div className="space-y-1.5 sm:col-span-6">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="smtp-pass">Пароль</Label>
                    {data?.has_password && !clearPassword && (
                      <span className="text-[10px] text-emerald-500 font-medium flex items-center gap-1">
                        <Key className="size-3" /> Пароль сохранён в SecBox
                      </span>
                    )}
                    {clearPassword && (
                      <span className="text-[10px] text-destructive font-medium">Будет удалён при сохранении</span>
                    )}
                  </div>
                  <Input
                    id="smtp-pass"
                    type="password"
                    placeholder={
                      clearPassword
                        ? "Пароль будет очищен"
                        : data?.has_password
                        ? "•••••••••••• (не изменен)"
                        : "Пароль приложения или токен"
                    }
                    value={password}
                    disabled={clearPassword}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  {data?.has_password && (
                    <div className="flex justify-end pt-0.5">
                      <button
                        type="button"
                        onClick={() => {
                          setClearPassword(!clearPassword)
                          setPassword("")
                        }}
                        className="text-[11px] text-destructive hover:underline flex items-center gap-1 cursor-pointer"
                      >
                        <Trash2 className="size-3" />
                        {clearPassword ? "Отменить удаление пароля" : "Очистить сохранённый пароль"}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Отправитель (From) — общий для обоих режимов */}
          <div className="grid gap-4 sm:grid-cols-12 pt-2 border-t border-border/60">
            <div className="space-y-1.5 sm:col-span-6">
              <Label htmlFor="smtp-from">Адрес отправителя по умолчанию (From Email) *</Label>
              <Input
                id="smtp-from"
                type="email"
                placeholder="noreply@myshop.com"
                value={fromEmail}
                onChange={(e) => setFromEmail(e.target.value)}
              />
              <span className="text-[10px] text-muted-foreground">Email, от имени которого будут доставляться системные письма</span>
            </div>

            <div className="space-y-1.5 sm:col-span-6">
              <Label htmlFor="smtp-from-name">Имя отправителя (From Name, опционально)</Label>
              <Input
                id="smtp-from-name"
                placeholder="SaviorBill Shop, Техподдержка"
                value={fromName}
                onChange={(e) => setFromName(e.target.value)}
              />
              <span className="text-[10px] text-muted-foreground">Отображаемое имя в почтовом клиенте получателя</span>
            </div>
          </div>
        </CardContent>

        {canEdit ? (
          <CardFooter className="flex items-center justify-between gap-2 border-t pt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsResetDialogOpen(true)}
              disabled={saveMutation.isPending || resetMutation.isPending || !data?.configured}
              className="text-destructive border-destructive/30 hover:bg-destructive/10 gap-1.5"
            >
              <RotateCcw className="size-3.5" /> Сбросить настройки
            </Button>

            <Button
              size="sm"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending || resetMutation.isPending}
              className="gap-2"
            >
              {saveMutation.isPending && <Loader2 className="size-4 animate-spin" />}
              Сохранить настройки
            </Button>
          </CardFooter>
        ) : (
          <CardFooter className="border-t pt-4 text-xs text-muted-foreground">
            Режим только для чтения. Для изменения настроек почты требуются права администратора.
          </CardFooter>
        )}
      </Card>

      {/* Карточка 2: Тестовая отправка */}
      <Card className="bg-card/70 border-border/80 shadow-2xs">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Send className="size-4 text-primary" /> Проверка доставки (Тест транспорта)
          </CardTitle>
          <CardDescription className="text-xs">
            Отправьте тестовое письмо через текущий настроенный транспорт ({driver === "lua" ? "Lua-скрипт API" : "SMTP"}).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5 sm:col-span-1">
              <Label htmlFor="test-email">Email получателя *</Label>
              <Input
                id="test-email"
                placeholder="your-email@example.com"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
              />
            </div>
            <div className="space-y-1.5 sm:col-span-1">
              <Label htmlFor="test-from-email">Переопределить From Email (опционально)</Label>
              <Input
                id="test-from-email"
                placeholder={fromEmail || "custom-from@domain.com"}
                value={testFromEmail}
                onChange={(e) => setTestFromEmail(e.target.value)}
              />
            </div>
            <div className="space-y-1.5 sm:col-span-1">
              <Label htmlFor="test-from-name">Переопределить From Name (опционально)</Label>
              <Input
                id="test-from-name"
                placeholder={fromName || "Custom Sender Name"}
                value={testFromName}
                onChange={(e) => setTestFromName(e.target.value)}
              />
            </div>
          </div>

          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={() => testMutation.mutate()}
              disabled={testMutation.isPending || !testEmail}
              className="gap-2"
            >
              {testMutation.isPending ? (
                <>
                  <Loader2 className="size-4 animate-spin" /> Отправка через {driver === "lua" ? "Lua API" : "SMTP"}…
                </>
              ) : (
                <>
                  <Send className="size-4" /> Отправить тестовое письмо
                </>
              )}
            </Button>
          </div>

          {/* Результат проверки */}
          {testResult && (
            <div
              className={`rounded-xl border p-3.5 text-xs flex items-start gap-2.5 transition-all ${
                testResult.ok
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                  : "bg-destructive/10 border-destructive/30 text-destructive"
              }`}
            >
              {testResult.ok ? (
                <CheckCircle2 className="size-4 shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="size-4 shrink-0 mt-0.5" />
              )}
              <div className="space-y-1 flex-1">
                <div className="font-semibold">{testResult.ok ? "Успешная доставка" : "Ошибка доставки"}</div>
                <div className="font-mono text-[11px] whitespace-pre-wrap break-all">{testResult.message}</div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Диалог подтверждения сброса */}
      <AlertDialog open={isResetDialogOpen} onOpenChange={setIsResetDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Сбросить настройки почтового транспорта?</AlertDialogTitle>
            <AlertDialogDescription>
              Все сохранённые параметры почты (выбранный драйвер, SMTP-хост, логин, пароль, привязанный Lua-скрипт) будут удалены из базы данных.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => resetMutation.mutate()}
              className="bg-destructive hover:bg-destructive/90 text-white"
            >
              Сбросить настройки
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
