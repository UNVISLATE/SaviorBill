import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { Badge } from "@/components/shadsnui/badge"
import { Input } from "@/components/shadsnui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"

interface RateLimitRule {
  kind: string
  max_hits: number
  window: number
  overridden: boolean
}

const KIND_LABEL: Record<string, string> = {
  default: "По умолчанию",
  auth: "Аутентификация",
  mail: "Почта",
  sensitive: "Чувствительные операции",
}

export function RateLimitSettings() {
  const qc = useQueryClient()
  const [drafts, setDrafts] = useState<Record<string, { max_hits: string; window: string }>>({})

  const { data, isLoading } = useQuery({
    queryKey: ["admin-ratelimits"],
    queryFn: async () => (await api.get<RateLimitRule[]>("/v1/admin/settings/ratelimits")).data,
  })

  const save = useMutation({
    mutationFn: async (kind: string) => {
      const d = drafts[kind]
      const rule = data?.find((r) => r.kind === kind)
      await api.put(`/v1/admin/settings/ratelimits/${kind}`, {
        max_hits: Number(d?.max_hits ?? rule?.max_hits),
        window: Number(d?.window ?? rule?.window),
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-ratelimits"] })
      toastSuccess("Лимит обновлён")
    },
    onError: () => toastError("Не удалось обновить лимит"),
  })

  const reset = useMutation({
    mutationFn: async (kind: string) => {
      await api.delete(`/v1/admin/settings/ratelimits/${kind}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-ratelimits"] })
      toastSuccess("Сброшено к значению из окружения")
    },
    onError: () => toastError("Не удалось сбросить лимит"),
  })

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Rate limiting</h2>
        <p className="text-sm text-muted-foreground">
          Переопределения хранятся в таблице settings и применяются немедленно, без
          перезапуска сервиса. Без переопределения действует значение из окружения (ENV).
        </p>
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Категория</TableHead>
              <TableHead>Запросов</TableHead>
              <TableHead>Окно (сек)</TableHead>
              <TableHead>Источник</TableHead>
              <TableHead className="w-48" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                  Загрузка…
                </TableCell>
              </TableRow>
            )}
            {data?.map((r) => {
              const draft = drafts[r.kind] ?? { max_hits: String(r.max_hits), window: String(r.window) }
              return (
                <TableRow key={r.kind}>
                  <TableCell className="font-medium">{KIND_LABEL[r.kind] ?? r.kind}</TableCell>
                  <TableCell>
                    <Input
                      type="number"
                      min={1}
                      className="w-24"
                      value={draft.max_hits}
                      onChange={(e) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [r.kind]: { ...draft, max_hits: e.target.value },
                        }))
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Input
                      type="number"
                      min={1}
                      className="w-24"
                      value={draft.window}
                      onChange={(e) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [r.kind]: { ...draft, window: e.target.value },
                        }))
                      }
                    />
                  </TableCell>
                  <TableCell>
                    {r.overridden ? (
                      <Badge variant="outline">переопределено</Badge>
                    ) : (
                      <Badge variant="secondary">ENV</Badge>
                    )}
                  </TableCell>
                  <TableCell className="flex gap-2">
                    <Button size="sm" onClick={() => save.mutate(r.kind)} disabled={save.isPending}>
                      Сохранить
                    </Button>
                    {r.overridden && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => reset.mutate(r.kind)}
                        disabled={reset.isPending}
                      >
                        Сбросить
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
