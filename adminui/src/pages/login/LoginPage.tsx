import { useState, type FormEvent } from "react"
import { Navigate, useLocation } from "react-router-dom"

import { useAuth } from "@/hooks/use-auth"
import { Button } from "@/components/shadsnui/button"
import { Field, FieldError, FieldLabel } from "@/components/shadsnui/field"
import { Input } from "@/components/shadsnui/input"

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
    <div className="flex min-h-svh flex-col items-center justify-center gap-4 bg-muted/40 p-4 md:p-10">
      <div className="flex w-full max-w-sm flex-col gap-4">
        <div className="flex items-center gap-2 self-center font-medium">
          <img src="/unvi/logo_1x1_32.webp" alt="unvi.xyz" className="size-8" />
          <h1 className="text-lg font-semibold">SaviorBill Admin</h1>
        </div>
        <form
          onSubmit={onSubmit}
          className="w-full max-w-sm space-y-6 rounded-xl border bg-background p-8 shadow-sm"
        >
          <Field>
            <FieldLabel htmlFor="login">Логин или email</FieldLabel>
            <Input
              id="login"
              autoComplete="username"
              value={loginValue}
              onChange={(e) => setLoginValue(e.target.value)}
              required
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
      </div>
    </div>
  )
}
