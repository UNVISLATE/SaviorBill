import { useState, type FormEvent } from "react"
import { Navigate, useLocation } from "react-router-dom"

import { useAuth } from "@/hooks/use-auth"
import { Button } from "@/components/shadsnui/button"
import { Field, FieldError, FieldLabel } from "@/components/shadsnui/field"
import { Input } from "@/components/shadsnui/input"
import { Separator } from "@/components/shadsnui/separator"

export function LoginPage() {
  const { login, isAuthenticated } = useAuth()
  const location = useLocation()
  const [loginValue, setLoginValue] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  if (isAuthenticated) {
    const from = (location.state as { from?: string } | null)?.from ?? "/"
    return <Navigate to={from} replace />
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    try {
      await login(loginValue, password)
    } catch {
      // Анти-энумерация (см. src/api/v1/auth/local.py) — backend не различает
      // "нет такого логина" и "неверный пароль", UI повторяет ту же анонимность.
      setError("Неверный логин или пароль")
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="relative flex min-h-svh flex-col items-center justify-center overflow-hidden bg-background p-4 md:p-10">
      {/* Декоративное радиальное свечение брендовым цветом — чисто фон, не несёт смысла. */}
      <div
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            "radial-gradient(60% 50% at 50% 0%, rgba(0,144,128,0.16), transparent 70%)",
        }}
      />
      <div className="flex w-full max-w-sm flex-col gap-6">
        <div className="flex items-center gap-2 self-center font-medium">
          <img src="/unvi/logo_1x1_128.webp" alt="unvi.xyz" className="size-9" />
          <h1 className="text-lg font-semibold">SaviorBill Admin</h1>
        </div>
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

          {/* OAuth-провайдеры backend'ом пока не отдаются (нет /v1/auth/oauth/providers
              и коллбэков) — намеренно оставлено как отключённый, но видимый задел,
              чтобы не переверстывать форму при подключении. */}
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <Separator className="flex-1" />
              <span className="text-xs text-muted-foreground">или</span>
              <Separator className="flex-1" />
            </div>
            <div className="grid gap-2">
              <Button variant="outline" className="w-full" disabled title="Скоро">
                Продолжить с Google
              </Button>
              <Button variant="outline" className="w-full" disabled title="Скоро">
                Продолжить с GitHub
              </Button>
            </div>
            <p className="text-center text-xs text-muted-foreground">
              OAuth-вход появится позже
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

