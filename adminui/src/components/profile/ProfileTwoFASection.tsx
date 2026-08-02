import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { KeyRound, Loader2, ShieldCheck, ShieldOff } from "lucide-react"
import QRCode from "qrcode"

import { api } from "@/api/api.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { Alert, AlertDescription, AlertTitle } from "@/components/shadsnui/alert"
import { Button } from "@/components/shadsnui/button"
import { Field, FieldDescription, FieldLabel } from "@/components/shadsnui/field"
import { Input } from "@/components/shadsnui/input"
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSeparator,
  InputOTPSlot,
} from "@/components/shadsnui/input-otp"
import { Skeleton } from "@/components/shadsnui/skeleton"
import { Separator } from "@/components/shadsnui/separator"

interface TwoFAStatus {
  enabled: boolean
  required: boolean
  recovery_codes_left: number
}

interface TwoFASetup {
  secret: string
  otpauth_url: string
}

/** Двухфакторка своего же аккаунта — управление доступно только в режиме
 * "own" (см. ProfileDialogHost — раздел добавляется с `ownOnly: true`),
 * админ не может включать/выключать 2FA за другого пользователя.
 *
 * QR-код рисуется на клиенте из `otpauth_url` (пакет `qrcode`, чистый JS,
 * без сетевых запросов к сторонним генераторам QR — секрет 2FA никуда не
 * уходит с клиента). Секрет/ссылка ниже остаются как копируемый текст —
 * запасной вариант для ручного ввода, если не получается отсканировать.
 */
export function ProfileTwoFASection() {
  const qc = useQueryClient()
  const [setup, setSetup] = useState<TwoFASetup | null>(null)
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null)
  const [confirmCode, setConfirmCode] = useState("")
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null)
  const [disableOpen, setDisableOpen] = useState(false)
  const [disablePassword, setDisablePassword] = useState("")
  const [disableCode, setDisableCode] = useState("")

  const { data: status, isLoading } = useQuery({
    queryKey: ["twofa-status"],
    queryFn: async () => (await api.get<TwoFAStatus>("/v1/user/me/2fa")).data,
  })

  const startSetup = useMutation({
    mutationFn: async () => (await api.post<TwoFASetup>("/v1/user/me/2fa/setup")).data,
    onSuccess: (data) => {
      setSetup(data)
      setConfirmCode("")
    },
    onError: () => toastError("Не удалось начать настройку 2FA"),
  })

  useEffect(() => {
    if (!setup) {
      setQrDataUrl(null)
      return
    }
    let cancelled = false
    QRCode.toDataURL(setup.otpauth_url, { width: 220, margin: 1 })
      .then((url) => {
        if (!cancelled) setQrDataUrl(url)
      })
      .catch(() => {
        if (!cancelled) setQrDataUrl(null)
      })
    return () => {
      cancelled = true
    }
  }, [setup])

  const confirmSetup = useMutation({
    mutationFn: async () =>
      (await api.post<{ recovery_codes: string[] }>("/v1/user/me/2fa/enable", { code: confirmCode })).data,
    onSuccess: (data) => {
      setRecoveryCodes(data.recovery_codes)
      setSetup(null)
      setConfirmCode("")
      toastSuccess("Двухфакторная аутентификация включена")
      void qc.invalidateQueries({ queryKey: ["twofa-status"] })
    },
    onError: () => toastError("Неверный код — попробуйте ещё раз"),
  })

  const disable = useMutation({
    mutationFn: async () =>
      api.post("/v1/user/me/2fa/disable", {
        password: disablePassword || undefined,
        code: disableCode || undefined,
      }),
    onSuccess: () => {
      toastSuccess("Двухфакторная аутентификация отключена")
      setDisableOpen(false)
      setDisablePassword("")
      setDisableCode("")
      void qc.invalidateQueries({ queryKey: ["twofa-status"] })
    },
    onError: () => toastError("Не удалось отключить 2FA", "проверьте пароль/код"),
  })

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-20 w-full" />
      </div>
    )
  }

  // Коды восстановления показываются один раз сразу после включения —
  // отдельный экран поверх остального, чтобы их точно не потеряли не глядя.
  if (recoveryCodes) {
    return (
      <div className="space-y-4">
        <Alert>
          <ShieldCheck className="size-4" />
          <AlertTitle>Сохраните коды восстановления</AlertTitle>
          <AlertDescription>
            Они показываются только один раз. Каждый код можно использовать
            вместо кода из приложения-аутентификатора один раз (например, при
            потере телефона).
          </AlertDescription>
        </Alert>
        <div className="grid grid-cols-2 gap-2 rounded-md border bg-muted/40 p-3 font-mono text-sm">
          {recoveryCodes.map((code) => (
            <span key={code} className="select-all">{code}</span>
          ))}
        </div>
        <Button onClick={() => setRecoveryCodes(null)}>Готово, я их сохранил(а)</Button>
      </div>
    )
  }

  if (status?.enabled) {
    return (
      <div className="space-y-4">
        <Alert>
          <ShieldCheck className="size-4" />
          <AlertTitle>Двухфакторная аутентификация включена</AlertTitle>
          <AlertDescription>
            Осталось кодов восстановления: {status.recovery_codes_left}.
            {status.required && " Для вашей роли 2FA обязательна настройкой инстанса — отключить не получится, пока это требование не снимет владелец/админ."}
          </AlertDescription>
        </Alert>
        {!status.required && (
          <>
            {!disableOpen ? (
              <Button variant="outline" onClick={() => setDisableOpen(true)}>
                <ShieldOff className="size-4" /> Отключить 2FA
              </Button>
            ) : (
              <div className="space-y-3 rounded-md border p-3">
                <p className="text-sm text-muted-foreground">
                  Подтвердите паролем (или кодом 2FA/восстановления, если у
                  аккаунта нет пароля).
                </p>
                <Field>
                  <FieldLabel htmlFor="disable-pass">Текущий пароль</FieldLabel>
                  <Input
                    id="disable-pass"
                    type="password"
                    value={disablePassword}
                    onChange={(e) => setDisablePassword(e.target.value)}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="disable-code">…или код 2FA/восстановления</FieldLabel>
                  <Input
                    id="disable-code"
                    value={disableCode}
                    onChange={(e) => setDisableCode(e.target.value)}
                  />
                </Field>
                <div className="flex gap-2">
                  <Button
                    variant="destructive"
                    disabled={disable.isPending || (!disablePassword && !disableCode)}
                    onClick={() => disable.mutate()}
                  >
                    {disable.isPending && <Loader2 className="size-4 animate-spin" />}
                    Отключить
                  </Button>
                  <Button variant="ghost" onClick={() => setDisableOpen(false)}>Отмена</Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    )
  }

  if (setup) {
    return (
      <div className="space-y-4">
        <Alert>
          <KeyRound className="size-4" />
          <AlertTitle>Отсканируйте QR-код в приложении-аутентификаторе</AlertTitle>
          <AlertDescription>
            Google Authenticator, Authy, 1Password и т.п. Если сканировать
            нельзя — введите секрет вручную ниже.
          </AlertDescription>
        </Alert>
        <div className="flex justify-center rounded-md border bg-white p-4">
          {qrDataUrl ? (
            <img src={qrDataUrl} alt="QR-код для настройки 2FA" width={220} height={220} />
          ) : (
            <Skeleton className="h-[220px] w-[220px]" />
          )}
        </div>
        <Field>
          <FieldLabel>Секрет (для ручного ввода)</FieldLabel>
          <Input readOnly value={setup.secret} onFocus={(e) => e.currentTarget.select()} className="font-mono" />
        </Field>
        <Separator />
        <Field>
          <FieldLabel htmlFor="confirm-code">Код из приложения</FieldLabel>
          <InputOTP
            id="confirm-code"
            maxLength={6}
            value={confirmCode}
            onChange={setConfirmCode}
            autoFocus
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
          <FieldDescription>Введите текущий код, чтобы подтвердить настройку.</FieldDescription>
        </Field>
        <div className="flex gap-2">
          <Button
            disabled={confirmCode.length < 6 || confirmSetup.isPending}
            onClick={() => confirmSetup.mutate()}
          >
            {confirmSetup.isPending && <Loader2 className="size-4 animate-spin" />}
            Подтвердить и включить
          </Button>
          <Button variant="ghost" onClick={() => setSetup(null)}>Отмена</Button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <Alert>
        <ShieldOff className="size-4" />
        <AlertTitle>Двухфакторная аутентификация отключена</AlertTitle>
        <AlertDescription>
          {status?.required
            ? "Для вашей роли она обязательна настройкой инстанса — включите, чтобы не потерять доступ к действиям в админке."
            : "Дополнительная защита входа кодом из приложения-аутентификатора."}
        </AlertDescription>
      </Alert>
      <Button disabled={startSetup.isPending} onClick={() => startSetup.mutate()}>
        {startSetup.isPending && <Loader2 className="size-4 animate-spin" />}
        Включить 2FA
      </Button>
    </div>
  )
}
