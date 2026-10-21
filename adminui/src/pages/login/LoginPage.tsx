import { useState, type FormEvent } from "react"
import { Navigate, useLocation, useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/api/api"
import { KeyRound, ShieldCheck } from "lucide-react"

import { useAuth } from "@/hooks/use-auth"
import { useBranding } from "@/hooks/use-branding"
import { Button } from "@/components/shadsnui/button"
import { Field, FieldError, FieldLabel } from "@/components/shadsnui/field"
import { Input } from "@/components/shadsnui/input"
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSeparator,
  InputOTPSlot,
} from "@/components/shadsnui/input-otp"
import { Separator } from "@/components/shadsnui/separator"
import { Logo } from "@/components/layout/Logo"

/** Отдельный экран второго фактора — показывается ПОСЛЕ успешной проверки
 * логина/пароля (см. родителя): backend не разглашает заранее, включена ли
 * 2FA у аккаунта (иначе форма выдавала бы это простым перебором логина), а
 * раз мы уже здесь — значит пара логин/пароль верна и остался только код. */
function TotpStep({
  onSubmit,
  onBack,
  pending,
  error,
}: {
  onSubmit: (code: string) => void
  onBack: () => void
  pending: boolean
  error: string | null
}) {
  const [useRecovery, setUseRecovery] = useState(false)
  const [otp, setOtp] = useState("")
  const [recoveryCode, setRecoveryCode] = useState("")

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    onSubmit(useRecovery ? recoveryCode.trim() : otp)
  }

  return (
    <div className="w-full max-w-sm space-y-6 rounded-xl border bg-card/60 p-8 shadow-lg ring-1 ring-foreground/5 backdrop-blur-sm">
      <div className="space-y-1 text-center">
        <ShieldCheck className="mx-auto size-8 text-primary" />
        <h2 className="text-base font-semibold">Двухфакторная аутентификация</h2>
        <p className="text-sm text-muted-foreground">
          {useRecovery
            ? "Введите один из кодов восстановления."
            : "Введите 6-значный код из приложения-аутентификатора."}
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {!useRecovery ? (
          <Field>
            <div className="flex justify-center">
              <InputOTP
                maxLength={6}
                value={otp}
                onChange={setOtp}
                autoFocus
                containerClassName="justify-center"
              >
                <InputOTPGroup>
                  <InputOTPSlot index={0} />
                  <InputOTPSlot index={1} />
                  <InputOTPSlot index={2} />
                </InputOTPGroup>
                <InputOTPSeparator />
                <InputOTPGroup>
                  <InputOTPSlot index={3} />
                  <InputOTPSlot index={4} />
                  <InputOTPSlot index={5} />
                </InputOTPGroup>
              </InputOTP>
            </div>
            {error && <FieldError className="text-center">{error}</FieldError>}
          </Field>
        ) : (
          <Field>
            <FieldLabel htmlFor="recovery-code">Код восстановления</FieldLabel>
            <Input
              id="recovery-code"
              autoFocus
              autoComplete="one-time-code"
              placeholder="напр. a1b2c3d4e5"
              value={recoveryCode}
              onChange={(e) => setRecoveryCode(e.target.value)}
              className="font-mono"
            />
            {error && <FieldError>{error}</FieldError>}
          </Field>
        )}

        <Button
          type="submit"
          className="w-full"
          disabled={pending || (useRecovery ? !recoveryCode.trim() : otp.length < 6)}
        >
          {pending ? "Проверка…" : "Подтвердить"}
        </Button>

        <div className="flex items-center justify-between text-sm">
          <button
            type="button"
            className="text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            onClick={onBack}
          >
            Назад
          </button>
          <button
            type="button"
            className="flex items-center gap-1 text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            onClick={() => {
              setUseRecovery((v) => !v)
              setOtp("")
              setRecoveryCode("")
            }}
          >
            <KeyRound className="size-3.5" />
            {useRecovery ? "Ввести код из приложения" : "Использовать код восстановления"}
          </button>
        </div>
      </form>
    </div>
  )
}

interface OAuthProviderPublic {
  slug: string
  title: string
  icon_url: string | null
}

export function LoginPage() {
  const { login, isAuthenticated } = useAuth()
  const branding = useBranding()
  const location = useLocation()
  const navigate = useNavigate()
  const [loginValue, setLoginValue] = useState("")
  const [password, setPassword] = useState("")
  const [totpRequired, setTotpRequired] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [totpError, setTotpError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [pendingOAuth, setPendingOAuth] = useState<string | null>(null)

  const { data: oauthProviders = [] } = useQuery({
    queryKey: ["oauth-providers-public"],
    queryFn: async () => (await api.get<OAuthProviderPublic[]>("/v1/oauth/providers")).data,
    retry: false,
  })

  const searchParams = new URLSearchParams(location.search)
  const from = searchParams.get("from") || (location.state as { from?: string } | null)?.from || "/"

  if (isAuthenticated) {
    return <Navigate to={from} replace />
  }

  const handleOAuthStart = async (slug: string) => {
    setPendingOAuth(slug)
    try {
      const res = await api.get<{ authorize_url: string }>(`/v1/oauth/${slug}`)
      if (res.data.authorize_url) {
        window.location.assign(res.data.authorize_url)
      }
    } catch {
      setError("Не удалось запустить авторизацию через OAuth")
      setPendingOAuth(null)
    }
  }

  async function attemptLogin(totp?: string) {
    setPending(true)
    try {
      await login(loginValue, password, totp)
      navigate(from, { replace: true })
      return true
    } catch (err) {
      if (err instanceof Error && err.message === "TOTP_REQUIRED") {
        setTotpRequired(true)
        setTotpError(null)
      } else if (err instanceof Error && err.message === "TOTP_INVALID") {
        setTotpRequired(true)
        setTotpError("Неверный код — попробуйте ещё раз")
      } else if (err instanceof Error && err.message === "ACCESS_DENIED") {
        setError("Доступ запрещён: у вашей роли нет прав на вход в админ-панель")
      } else {
        // Анти-энумерация (см. src/api/v1/auth/local.py) — backend не
        // различает "нет такого логина" и "неверный пароль", UI повторяет ту
        // же анонимность.
        setError("Неверный логин или пароль")
      }
      return false
    } finally {
      setPending(false)
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    await attemptLogin()
  }

  async function onSubmitTotp(code: string) {
    setTotpError(null)
    const ok = await attemptLogin(code)
    if (!ok) return
  }

  return (
    <div className="relative flex min-h-svh flex-col items-center justify-center overflow-hidden bg-background p-4 md:p-10">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <div className="flex flex-col items-center gap-3 self-center text-center select-none">
          <div className="flex items-center gap-2 font-medium">
            <Logo className="size-6" src={branding.logoUrl} />
            <h1 className="text-base font-semibold">{branding.name}</h1>
          </div>
        </div>

        {totpRequired ? (
          <TotpStep
            onSubmit={onSubmitTotp}
            onBack={() => {
              setTotpRequired(false)
              setTotpError(null)
            }}
            pending={pending}
            error={totpError}
          />
        ) : (
          <div className="w-full max-w-sm space-y-6 rounded-xl border bg-card/60 p-8 shadow-lg ring-1 ring-foreground/5 backdrop-blur-sm">
            <div className="space-y-1">
              <h2 className="text-base font-semibold">Вход в панель</h2>
              <p className="text-sm text-muted-foreground">
                Доступ только для сотрудников с ролью в системе.
              </p>
            </div>

            <form onSubmit={onSubmit} className="space-y-5">
              <Field>
                <FieldLabel htmlFor="login">Логин или email</FieldLabel>
                <Input
                  id="login"
                  autoComplete="username"
                  value={loginValue}
                  onChange={(e) => setLoginValue(e.target.value)}
                  required
                  autoFocus
                />
              </Field>

              <Field>
                <FieldLabel htmlFor="password">Пароль</FieldLabel>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                {error && <FieldError>{error}</FieldError>}
              </Field>

              <Button type="submit" className="w-full" disabled={pending}>
                {pending ? "Вход…" : "Войти"}
              </Button>
            </form>

            {oauthProviders.length > 0 && (
              <div className="space-y-3 pt-1">
                <div className="flex items-center gap-3">
                  <Separator className="flex-1" />
                  <span className="text-xs text-muted-foreground">или через OAuth</span>
                  <Separator className="flex-1" />
                </div>
                <div className="grid gap-2">
                  {oauthProviders.map((p) => (
                    <Button
                      key={p.slug}
                      type="button"
                      variant="outline"
                      className="w-full gap-2 justify-center"
                      disabled={pendingOAuth !== null}
                      onClick={() => handleOAuthStart(p.slug)}
                    >
                      {p.icon_url && <img src={p.icon_url} alt="" className="size-4 object-contain" />}
                      {pendingOAuth === p.slug ? "Перенаправление…" : `Продолжить с ${p.title}`}
                    </Button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

