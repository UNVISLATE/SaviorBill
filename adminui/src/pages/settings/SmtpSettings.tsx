import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, Loader2, Mail, Send, Server, ShieldCheck, XCircle } from "lucide-react"

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
import { Switch } from "@/components/shadsnui/switch"

interface SmtpData {
  host: string | null
  port: number
  user: string | null
  has_password: boolean
  from_email: string | null
  use_tls: boolean
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
  const [user, setUser] = useState("")
  const [password, setPassword] = useState("")
  const [fromEmail, setFromEmail] = useState("")
  const [useTls, setUseTls] = useState(true)

  const [testEmail, setTestEmail] = useState("")
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)

  useEffect(() => {
    if (data) {
      setHost(data.host || "")
      setPort(data.port || 587)
      setUser(data.user || "")
      setPassword("")
      setFromEmail(data.from_email || "")
      setUseTls(data.use_tls)
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
        user: user.trim() || null,
        password: password || undefined,
        from_email: fromEmail.trim() || null,
        use_tls: useTls,
      })
    },
    onSuccess: () => {
      toastSuccess("Настройки SMTP успешно сохранены")
      setPassword("")
      void qc.invalidateQueries({ queryKey: ["admin-settings-smtp"] })
    },
    onError: (e) => toastError("Не удалось сохранить настройки SMTP", getErrorDetail(e)),
  })

  const testMutation = useMutation({
    mutationFn: async () => {
      return (
        await api.post<{ ok: boolean; message: string }>("/v1/admin/settings/smtp/test", {
          to_email: testEmail.trim(),
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
        <CardContent className="p-8 text-center text-sm text-muted-foreground flex items-center justify-center gap-2">
          <Loader2 className="size-4 animate-spin" /> Загрузка настроек SMTP…
        </CardContent>
      </Card>
    )
  }

  const isConfigured = Boolean(data?.host && data?.from_email)

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
                Параметры для отправки системных уведомлений, кодов подтверждения и чеков клиентам.
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
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="smtp-host">Хост сервера (SMTP Host) *</Label>
              <Input
                id="smtp-host"
                placeholder="smtp.mailgun.org, smtp.yandex.ru, smtp.gmail.com"
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
                placeholder="587 или 465"
                value={port}
                onChange={(e) => setPort(Number(e.target.value))}
              />
              <span className="text-[10px] text-muted-foreground">587 (STARTTLS) или 465 (SSL)</span>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="smtp-user">Логин / Пользователь</Label>
              <Input
                id="smtp-user"
                placeholder="user@example.com"
                value={user}
                onChange={(e) => setUser(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="smtp-pass">Пароль</Label>
                {data?.has_password && (
                  <span className="text-[10px] text-emerald-500 font-medium">✓ Пароль сохранён в SecBox</span>
                )}
              </div>
              <Input
                id="smtp-pass"
                type="password"
                placeholder={data?.has_password ? "•••••••••••• (не изменен)" : "Пароль приложения"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 pt-2 border-t">
            <div className="space-y-1.5">
              <Label htmlFor="smtp-from">Адрес отправителя (From Email) *</Label>
              <Input
                id="smtp-from"
                type="email"
                placeholder="noreply@myshop.com"
                value={fromEmail}
                onChange={(e) => setFromEmail(e.target.value)}
              />
              <span className="text-[10px] text-muted-foreground">Должен быть разрешён вашим SMTP-провайдером</span>
            </div>

            <div className="flex items-center justify-between rounded-xl border border-border/80 bg-muted/30 p-3 self-end h-[62px]">
              <div className="space-y-0.5">
                <Label className="text-xs font-medium flex items-center gap-1.5">
                  <ShieldCheck className="size-3.5 text-primary" /> Использовать TLS / STARTTLS
                </Label>
                <p className="text-[10px] text-muted-foreground">Шифрование соединения при отправке писем</p>
              </div>
              <Switch checked={useTls} onCheckedChange={setUseTls} />
            </div>
          </div>
        </CardContent>
        <CardFooter className="flex justify-end gap-2 border-t pt-4">
          <Button
            size="sm"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
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
            Отправьте тестовое письмо на свой email, чтобы убедиться в правильности логина, пароля и портов.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1 space-y-1">
              <Input
                placeholder="your-email@example.com"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
              />
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setTestResult(null)
                testMutation.mutate()
              }}
              disabled={testMutation.isPending || !testEmail.trim() || !isConfigured}
              className="gap-2 shrink-0"
            >
              {testMutation.isPending ? (
                <>
                  <Loader2 className="size-4 animate-spin" /> Отправка…
                </>
              ) : (
                <>
                  <Mail className="size-4" /> Отправить тест
                </>
              )}
            </Button>
          </div>

          {!isConfigured && (
            <p className="text-xs text-amber-500">
              Сначала сохраните хост и адрес отправителя выше, чтобы активировать проверку.
            </p>
          )}

          {testResult && (
            <div
              className={`p-3 rounded-xl border text-xs flex items-start gap-2 ${
                testResult.ok
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-500"
                  : "border-destructive/30 bg-destructive/10 text-destructive"
              }`}
            >
              {testResult.ok ? (
                <CheckCircle2 className="size-4 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="size-4 shrink-0 mt-0.5" />
              )}
              <div className="space-y-0.5">
                <span className="font-semibold">{testResult.ok ? "Успешно" : "Сбой отправки"}</span>
                <p className="break-all">{testResult.message}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default SmtpSettings
