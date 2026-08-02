import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { AxiosError } from "axios"

import { api } from "@/api/api.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { Field, FieldDescription, FieldLabel } from "@/components/shadsnui/field"
import { Input } from "@/components/shadsnui/input"
import { Switch } from "@/components/shadsnui/switch"
import { Skeleton } from "@/components/shadsnui/skeleton"

interface SettingRawOut {
  key: string
  value: string | null
  is_secret: boolean
  editable: boolean
}

/** Значение конкретной настройки, либо ``null``, если строки в БД ещё нет
 * (настройка объявлена в каталоге, но никогда не была установлена — сервер
 * тогда отвечает 404, а не пустой строкой). */
function useSettingValue(key: string) {
  return useQuery({
    queryKey: ["admin-setting", key],
    queryFn: async (): Promise<SettingRawOut | null> => {
      try {
        return (await api.get<SettingRawOut>(`/v1/admin/settings/raw/${encodeURIComponent(key)}`)).data
      } catch (err) {
        if ((err as AxiosError)?.response?.status === 404) return null
        throw err
      }
    },
  })
}

type FieldType = "text" | "int" | "bool" | "json"

/** Само поле ввода — монтируется РОВНО ОДИН РАЗ, когда `initialValue` уже
 * известен (родитель не рендерит его, пока запрос не завершился), поэтому
 * локальному состоянию не нужно досинхронизироваться с сервером через
 * `useEffect` (тот запрещён линтером проекта для синхронного `setState` в
 * эффекте — да и сам по себе является анти-паттерном, если можно просто
 * взять начальное значение из пропа при инициализации `useState`). */
function SettingFieldInner({
  settingKey,
  label,
  hint,
  type,
  placeholder,
  initialValue,
}: {
  settingKey: string
  label: string
  hint?: string
  type: FieldType
  placeholder?: string
  initialValue: string
}) {
  const qc = useQueryClient()
  const [value, setValue] = useState(initialValue)

  const save = useMutation({
    mutationFn: async (v: string) => {
      await api.put(`/v1/admin/settings/raw/${encodeURIComponent(settingKey)}`, { value: v })
    },
    onSuccess: () => {
      toastSuccess(`Настройка «${label}» сохранена`)
      void qc.invalidateQueries({ queryKey: ["admin-setting", settingKey] })
    },
    onError: () => toastError(`Не удалось сохранить «${label}»`),
  })

  if (type === "bool") {
    const boolValue = value.toLowerCase() === "true"
    return (
      <Field orientation="horizontal" className="items-center justify-between gap-4">
        <div className="space-y-0.5">
          <FieldLabel>{label}</FieldLabel>
          {hint && <FieldDescription>{hint}</FieldDescription>}
        </div>
        <Switch
          checked={boolValue}
          onCheckedChange={(checked) => {
            setValue(String(checked))
            save.mutate(String(checked))
          }}
        />
      </Field>
    )
  }

  const changed = value !== initialValue

  return (
    <Field>
      <FieldLabel htmlFor={`setting-${settingKey}`}>{label}</FieldLabel>
      <div className="flex gap-2">
        <Input
          id={`setting-${settingKey}`}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          inputMode={type === "int" ? "numeric" : undefined}
          className={type === "json" ? "font-mono text-xs" : undefined}
        />
        <Button
          size="sm"
          variant="outline"
          disabled={!changed || save.isPending}
          onClick={() => save.mutate(value)}
        >
          Сохранить
        </Button>
      </div>
      {hint && <FieldDescription>{hint}</FieldDescription>}
    </Field>
  )
}

/**
 * Одно поле настройки из каталога (`core/settings_def.py`), напрямую поверх
 * `PUT/GET /admin/settings/raw/{key}` — без похода в общий Raw-редактор.
 * Раньше единственным способом поменять `billing.currency`/`auth.2fa.*` и
 * т.п. было редактирование сырых ключей вручную (см. PLAN.md).
 */
export function SettingField({
  settingKey,
  label,
  hint,
  type = "text",
  placeholder,
}: {
  settingKey: string
  label: string
  hint?: string
  type?: FieldType
  placeholder?: string
}) {
  const { data, isLoading } = useSettingValue(settingKey)

  if (isLoading) {
    return (
      <Field>
        <FieldLabel>{label}</FieldLabel>
        <Skeleton className="h-9 w-full" />
      </Field>
    )
  }

  return (
    <SettingFieldInner
      key={settingKey}
      settingKey={settingKey}
      label={label}
      hint={hint}
      type={type}
      placeholder={placeholder}
      initialValue={data?.value ?? ""}
    />
  )
}
