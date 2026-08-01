import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { RotateCcw, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { toastError, toastSuccess } from "@/lib/toast"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"

interface DlqItem {
  id: string
  fields: Record<string, string>
}

interface DlqQueueOverview {
  total: number
  items: DlqItem[]
}

type DlqOverview = Record<string, DlqQueueOverview>

const QUEUE_TITLES: Record<string, string> = {
  billing: "Биллинг",
  media_tasks: "Медиа: конвертация",
  media_results: "Медиа: результаты",
}

/** Мёртвые очереди (DLQ) — задачи, исчерпавшие попытки, раньше просто
 * копились в Valkey навсегда без единого способа их увидеть или повторить
 * (см. AUDIT.md §2.3, backend — Ф2 `services/dlq.py`). Один повтор/удаление
 * за раз — намеренно (это разбор конкретных сломанных задач, не массовая
 * операция). */
export function SystemDlq() {
  const { can } = useAuth()
  const qc = useQueryClient()
  const [queue, setQueue] = useState<string>("billing")
  const canRetry = can("system.tasks.retry")

  const { data, isLoading } = useQuery({
    queryKey: ["system-dlq"],
    queryFn: async () => (await api.get<DlqOverview>("/v1/admin/tasks/dlq")).data,
    refetchInterval: 5000,
  })

  const retry = useMutation({
    mutationFn: async (entryId: string) =>
      api.post(`/v1/admin/tasks/dlq/${queue}/${entryId}/retry`),
    onSuccess: () => {
      toastSuccess("Задача возвращена в рабочую очередь")
      void qc.invalidateQueries({ queryKey: ["system-dlq"] })
    },
    onError: () => toastError("Не удалось повторить задачу"),
  })

  const drop = useMutation({
    mutationFn: async (entryId: string) =>
      api.delete(`/v1/admin/tasks/dlq/${queue}/${entryId}`),
    onSuccess: () => {
      toastSuccess("Запись удалена из DLQ")
      void qc.invalidateQueries({ queryKey: ["system-dlq"] })
    },
    onError: () => toastError("Не удалось удалить запись"),
  })

  const current = data?.[queue]

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-semibold">Мёртвые очереди (DLQ)</h2>
          <p className="text-sm text-muted-foreground">
            Задачи, исчерпавшие попытки исполнения — без ручного разбора
            остаются потерянными навсегда.
          </p>
        </div>
        <Select value={queue} onValueChange={(v) => v && setQueue(v)}>
          <SelectTrigger size="sm" className="w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.keys(QUEUE_TITLES).map((q) => (
              <SelectItem key={q} value={q}>
                {QUEUE_TITLES[q]}
                {data?.[q] ? ` (${data[q].total})` : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex gap-2">
        {Object.entries(QUEUE_TITLES).map(([q, title]) => (
          <Badge key={q} variant={data?.[q]?.total ? "destructive" : "outline"}>
            {title}: {data?.[q]?.total ?? 0}
          </Badge>
        ))}
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID записи</TableHead>
              <TableHead>Поля</TableHead>
              {canRetry && <TableHead className="w-32">Действия</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={canRetry ? 3 : 2} className="py-8 text-center text-sm text-muted-foreground">
                  Загрузка…
                </TableCell>
              </TableRow>
            )}
            {!isLoading && (current?.items.length ?? 0) === 0 && (
              <TableRow>
                <TableCell colSpan={canRetry ? 3 : 2} className="py-8 text-center text-sm text-muted-foreground">
                  Пусто — мёртвых задач в этой очереди нет.
                </TableCell>
              </TableRow>
            )}
            {current?.items.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-mono text-xs">{item.id}</TableCell>
                <TableCell>
                  <pre className="max-w-md overflow-x-auto text-xs text-muted-foreground">
                    {JSON.stringify(item.fields, null, 2)}
                  </pre>
                </TableCell>
                {canRetry && (
                  <TableCell>
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 px-2"
                        disabled={retry.isPending}
                        onClick={() => retry.mutate(item.id)}
                        title="Вернуть в рабочую очередь"
                      >
                        <RotateCcw className="size-3.5" />
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 px-2"
                        disabled={drop.isPending}
                        onClick={() => drop.mutate(item.id)}
                        title="Удалить без повтора"
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
