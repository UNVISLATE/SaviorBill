import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Check, Coins, Copy, Gift, Send, Share2, Sparkles, UserRound, UsersRound } from "lucide-react"

import { api } from "@/api/api.ts"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/shadsnui/avatar"
import { Button } from "@/components/shadsnui/button"
import { Card, CardContent } from "@/components/shadsnui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"
import { toastSuccess } from "@/lib/toast"
import { useInstanceCurrency } from "@/lib/currency"

interface ReferralItem {
  id: number
  login: string
  created_at: string
  avatar_url: string | null
}

interface AccountBrief {
  id: number
  ref_code: string | null
  referral_count: number
  bonus_balance: string
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    })
  } catch {
    return iso
  }
}

export function ProfileReferralsSection({
  mode,
  userId,
}: {
  mode: "own" | "view" | "create"
  userId?: number
}) {
  const [codeCopied, setCodeCopied] = useState(false)
  const { symbol } = useInstanceCurrency()

  // Получаем аккаунт для отображения ref_code и бонусного баланса
  const { data: account } = useQuery({
    queryKey: mode === "own" ? ["account-me"] : ["admin-user-profile", userId],
    queryFn: async () => {
      const url = mode === "own" ? "/v1/user/me" : `/v1/admin/users/${userId}/profile`
      return (await api.get<AccountBrief>(url)).data
    },
  })

  // Список приглашённых пользователей
  const { data: referrals, isLoading } = useQuery({
    queryKey: mode === "own" ? ["user-referrals"] : ["admin-user-referrals", userId],
    queryFn: async () => {
      const url = mode === "own" ? "/v1/user/me/referrals" : `/v1/admin/users/${userId}/referrals`
      return (await api.get<ReferralItem[]>(url)).data
    },
  })

  const refCode = account?.ref_code || ""

  function handleCopyCode() {
    if (!refCode) return
    void navigator.clipboard.writeText(refCode)
    setCodeCopied(true)
    toastSuccess("Реферальный код скопирован")
    setTimeout(() => setCodeCopied(false), 2000)
  }

  function handleShareTg() {
    if (!refCode) return
    const text = `Используй мой реферальный код при регистрации: ${refCode}`
    window.open(
      `https://t.me/share/url?url=${encodeURIComponent(window.location.origin)}&text=${encodeURIComponent(text)}`,
      "_blank",
    )
  }

  function handleShareVk() {
    if (!refCode) return
    const text = `Реферальный код для регистрации: ${refCode}`
    window.open(
      `https://vk.com/share.php?comment=${encodeURIComponent(text)}&url=${encodeURIComponent(window.location.origin)}`,
      "_blank",
    )
  }

  function handleShareNative() {
    if (!refCode || typeof navigator.share !== "function") return
    void navigator.share({
      title: "Реферальный код",
      text: `Мой реферальный код: ${refCode}`,
    })
  }

  return (
    <div className="space-y-6">
      {/* 1. Верхний блок: Приведи друга */}
      <Card className="border-primary/20 bg-card shadow-sm">
        <CardContent className="space-y-4 p-5">
          <div className="flex items-start gap-3">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Gift className="size-5" />
            </div>
            <div className="space-y-1">
              <h3 className="text-base font-bold tracking-tight">Приведи друга</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Приглашайте друзей и получайте бонусы на баланс за их регистрацию и покупки.
              </p>
            </div>
          </div>

          {/* Преимущества программы */}
          <div className="grid gap-2 rounded-xl bg-muted/30 p-3 sm:grid-cols-2">
            <div className="flex items-center gap-2 text-xs text-foreground/90">
              <Sparkles className="size-3.5 shrink-0 text-primary" />
              <span>Бонус другу при регистрации по вашему коду</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-foreground/90">
              <Coins className="size-3.5 shrink-0 text-emerald-500" />
              <span>Отчисления на бонусный баланс с покупок реферала</span>
            </div>
          </div>

          {/* Блок «Ваш код» + «Поделиться» */}
          <div className="space-y-3 pt-1">
            <div className="space-y-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Ваш код
              </span>
              <div className="flex max-w-sm items-center justify-between rounded-xl border border-border/80 bg-background px-3 py-2 shadow-xs transition focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/20">
                <span className="font-mono text-base font-bold tracking-widest text-foreground select-all">
                  {refCode || "—"}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  className="size-7 rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
                  onClick={handleCopyCode}
                  disabled={!refCode}
                  title="Скопировать код"
                >
                  {codeCopied ? (
                    <Check className="size-4 text-emerald-500" />
                  ) : (
                    <Copy className="size-4" />
                  )}
                </Button>
              </div>
            </div>

            {/* Иконки быстрого расшаривания */}
            {refCode && (
              <div className="flex items-center gap-2 pt-0.5">
                <span className="text-xs text-muted-foreground">Поделиться:</span>
                <button
                  type="button"
                  onClick={handleShareTg}
                  title="Поделиться в Telegram"
                  className="flex size-7 items-center justify-center rounded-full bg-[#229ED9]/15 text-[#229ED9] transition hover:bg-[#229ED9]/30 active:scale-95"
                >
                  <Send className="size-3.5" />
                </button>
                <button
                  type="button"
                  onClick={handleShareVk}
                  title="Поделиться во ВКонтакте"
                  className="flex size-7 items-center justify-center rounded-full bg-[#0077FF]/15 text-[#0077FF] text-[10px] font-black transition hover:bg-[#0077FF]/30 active:scale-95"
                >
                  VK
                </button>
                {typeof navigator.share === "function" && (
                  <button
                    type="button"
                    onClick={handleShareNative}
                    title="Другие приложения"
                    className="flex size-7 items-center justify-center rounded-full bg-muted text-muted-foreground transition hover:text-foreground active:scale-95"
                  >
                    <Share2 className="size-3.5" />
                  </button>
                )}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* 2. Компактная статистика (занимает минимум места) */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Ваша статистика
        </h4>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col justify-between rounded-xl border bg-card/60 p-3 sm:p-3.5">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Приглашено
            </span>
            <div className="mt-1 flex items-baseline gap-1.5 font-mono">
              <span className="text-xl font-bold tracking-tight text-foreground">
                {referrals?.length ?? account?.referral_count ?? 0}
              </span>
              <span className="text-xs font-normal text-muted-foreground">человек</span>
            </div>
          </div>

          <div className="flex flex-col justify-between rounded-xl border bg-card/60 p-3 sm:p-3.5">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Бонусный баланс
            </span>
            <div className="mt-1 flex items-baseline gap-1.5 font-mono">
              <span className="text-xl font-bold tracking-tight text-emerald-500 dark:text-emerald-400">
                {account?.bonus_balance ?? "0.00"}
              </span>
              <span className="text-xs font-normal text-muted-foreground">{symbol}</span>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Список приглашённых пользователей с комфортными отступами */}
      <div className="space-y-2.5">
        <h4 className="text-sm font-semibold tracking-tight">
          Приглашённые пользователи ({referrals?.length ?? 0})
        </h4>

        {isLoading ? (
          <div className="py-8 text-center text-xs text-muted-foreground">
            Загрузка списка приглашённых…
          </div>
        ) : !referrals?.length ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed bg-muted/10 px-8 py-10 text-center sm:px-14">
            <div className="flex size-11 items-center justify-center rounded-full bg-muted/50 text-muted-foreground mb-3">
              <UsersRound className="size-6 opacity-75" />
            </div>
            <p className="text-sm font-semibold text-foreground">
              Приглашённых пользователей пока нет
            </p>
            <p className="mt-1 max-w-sm text-xs text-muted-foreground leading-relaxed">
              Пользователи, зарегистрировавшиеся по вашему реферальному коду, отобразятся здесь.
            </p>
          </div>
        ) : (
          <div className="rounded-xl border bg-card overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-12"></TableHead>
                  <TableHead>Пользователь</TableHead>
                  <TableHead className="w-36 text-right">Дата регистрации</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {referrals.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="py-2.5">
                      <Avatar className="size-8">
                        {r.avatar_url && <AvatarImage src={r.avatar_url} alt={r.login} />}
                        <AvatarFallback className="bg-muted text-xs font-medium">
                          <UserRound className="size-4 text-muted-foreground" />
                        </AvatarFallback>
                      </Avatar>
                    </TableCell>
                    <TableCell className="py-2.5">
                      <div className="flex flex-col">
                        <span className="font-medium text-foreground">{r.login}</span>
                        <span className="text-[11px] text-muted-foreground">ID: {r.id}</span>
                      </div>
                    </TableCell>
                    <TableCell className="py-2.5 text-right font-mono text-xs text-muted-foreground">
                      {fmtDate(r.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  )
}
