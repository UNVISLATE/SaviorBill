import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertCircle,
  CheckCircle2,
  Clock,
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

interface SmtpData {
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
  const { me } = useAuth()
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["admin-settings-smtp"],
    queryFn: async () => (await api.get<SmtpData>("/v1/admin/settings/smtp")).data,
  })

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

  const saveMutation = useMutation({
    mutationFn: async () => {
      await api.post("/v1/admin/settings/smtp", {
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
      toastSuccess("Настройки SMTP успешно сохранены")
      setPassword("")
      setClearPassword(false)
      void qc.invalidateQueries({ queryKey: ["admin-settings-smtp"] })
    },
    onError: (e) => toastError("Не удалось сохранить настройки SMTP", getErrorDetail(e)),
  })

  const resetMutation = useMutation({
    mutationFn: async () => {
      await api.delete("/v1/admin/settings/smtp")
    },
    onSuccess: () => {
      toastSuccess("Настройки SMTP очищены")
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
          <Loader2 className="size-4 animate-spin" /> Загрузка настроек SMTP…
        </CardContent>
      </Card>
    )
  }

  const isConfigured = Boolean(data?.configured)

  return (
    <div className="space-y-6">
      {/* Карточка 1: Конфигурация SMTP */}
      <Card className="bg-card/70 border-border/80 shadow-2xs">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Server className="size-4 text-primary" /> Почтовый сервер (SMTP)
              </CardTitle>
              <CardDescription className="text-xs">
                Параметры подключения к почтовому серверу для отправки системных писем, кодов подтверждения и чеков клиентам.
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
          {/* Сетевые параметры */}
          <div className="grid gap-4 sm:grid-cols-4">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="smtp-host">Хост сервера (SMTP Host) *</Label>
              <Input
                id="smtp-host"
                placeholder="smtp.bz, smtp.mailgun.org, smtp.yandex.ru"
                value={host}
                onChange={(e) => setHost(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="smtp-port">Порт *</Label>
              <Input
                id="smtp-port"
                type="number"
                min={1}
                max={65535}
                placeholder="587, 465, 9465, 9587"
                value={port}
                onChange={(e) => setPort(Number(e.target.value))}
              />
              <span className="text-[10px] text-muted-foreground">Любой порт (587, 465, 9465, 9587…)</span>
            </div>

            <div className="space-y-1.5">
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
                  <SelectItem value="starttls">STARTTLS (587, 9587, 2525)</SelectItem>
                  <SelectItem value="ssl">SSL / Direct TLS (465, 9465)</SelectItem>
                  <SelectItem value="none">Без шифрования (25, 1025)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-4">
            <div className="space-y-1.5 sm:col-span-1">
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
              <span className="text-[10px] text-muted-foreground">Дефолт: 10с (защита от зависаний)</span>
            </div>

            <div className="space-y-1.5 sm:col-span-3">
              <div className="rounded-lg border border-border/60 bg-muted/20 p-2.5 text-[11px] text-muted-foreground">
                <strong className="text-foreground">Подсказка:</strong> Для серверов с нестандартными портами (например, <code className="text-primary font-mono">smtp.bz</code> на портах <code className="font-mono">9465</code> и <code className="font-mono">9587</code>) режим шифрования выбирается независимо от номера порта.
              </div>
            </div>
          </div>

          {/* Аутентификация */}
          <div className="grid gap-4 sm:grid-cols-2 pt-2 border-t border-border/60">
            <div className="space-y-1.5">
              <Label htmlFor="smtp-user">Логин / Пользователь</Label>
              <Input
                id="smtp-user"
                placeholder="user@example.com или API-логин"
                value={user}
                onChange={(e) => setUser(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
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

          {/* Отправитель (From) */}
          <div className="grid gap-4 sm:grid-cols-2 pt-2 border-t border-border/60">
            <div className="space-y-1.5">
              <Label htmlFor="smtp-from">Адрес отправителя (From Email) *</Label>
              <Input
                id="smtp-from"
                type="email"
                placeholder="noreply@myshop.com"
                value={fromEmail}
                onChange={(e) => setFromEmail(e.target.value)}
              />
              <span className="text-[10px] text-muted-foreground">Должен быть подтверждён вашим почтовым сервисом</span>
            </div>

            <div className="space-y-1.5">
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
      </Card>

      {/* Карточка 2: Тестовая отправка */}
      <Card className="bg-card/70 border-border/80 shadow-2xs">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Send className="size-4 text-primary" /> Проверка отправки (Тест SMTP)
          </CardTitle>
          <CardDescription className="text-xs">
            Отправьте тестовое письмо, чтобы в реальном времени проверить доступность порта, аутентификацию и доставку.
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
                  <Loader2 className="size-4 animate-spin" /> Подключение и отправка…
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
                <div className="font-semibold">{testResult.ok ? "Успешная доставка" : "Ошибка соединения / отправки"}</div>
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
            <AlertDialogTitle>Сбросить настройки почтового сервера?</AlertDialogTitle>
            <AlertDialogDescription>
              Все сохранённые параметры SMTP (хост, логин, пароль, отправитель) будут удалены из базы данных. Отправка почты будет приостановлена до повторной настройки.
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
