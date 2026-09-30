import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Ban, Plus, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/shadsnui/card"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"
import { toastError, toastSuccess } from "@/lib/toast"

interface BannedDomain {
  domain: string
  reason: string | null
  created_at: string
}

interface ImportItem {
  line: number
  value: string
  domain: string | null
  status: "new" | "existing" | "duplicate" | "invalid"
  reason: string | null
}

interface ImportPreview {
  items: ImportItem[]
  new_count: number
  existing_count: number
  duplicate_count: number
  invalid_count: number
}

function AddDomainDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [domain, setDomain] = useState("")
  const [reason, setReason] = useState("")
  const qc = useQueryClient()

  const reset = () => {
    setDomain("")
    setReason("")
  }

  const add = useMutation({
    mutationFn: async () => api.post("/v1/admin/settings/email-domains", { domain, reason: reason || null }),
    onSuccess: () => {
      toastSuccess(`Домен «${domain}» заблокирован`)
      onOpenChange(false)
      reset()
      void qc.invalidateQueries({ queryKey: ["admin-banned-domains"] })
    },
    onError: (e: unknown) => toastError("Не удалось добавить домен", getErrorDetail(e)),
  })

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Заблокировать домен</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Домен</Label>
            <Input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="tempmail.com" autoFocus />
          </div>
          <div className="space-y-1">
            <Label>Причина (опционально)</Label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="временная почта" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button disabled={domain.trim().length < 1 || add.isPending} onClick={() => add.mutate()}>
            Заблокировать
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Заблокированные для регистрации email-домены — попытка зарегистрироваться
 * с почтой на таком домене отклоняется на бэкенде (защита от временной
 * почты/спама). Список маленький — без пагинации, простая таблица. */
export function BannedDomainsSettings() {
  const { can } = useAuth()
  const [adding, setAdding] = useState(false)
  const [bulkOpen, setBulkOpen] = useState(false)
  const [bulkText, setBulkText] = useState("")
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const canEdit = can("settings.email_domains.edit")
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["admin-banned-domains"],
    queryFn: async () => (await api.get<BannedDomain[]>("/v1/admin/settings/email-domains")).data,
  })

  const remove = useMutation({
    mutationFn: async (domain: string) => api.delete(`/v1/admin/settings/email-domains/${encodeURIComponent(domain)}`),
    onSuccess: () => {
      toastSuccess("Домен разблокирован")
      void qc.invalidateQueries({ queryKey: ["admin-banned-domains"] })
    },
    onError: (e: unknown) => toastError("Не удалось разблокировать домен", getErrorDetail(e)),
  })

  const bulkPreview = useMutation({
    mutationFn: async () => (
      await api.post<ImportPreview>("/v1/admin/settings/email-domains/bulk/preview", {
        raw_text: bulkText,
      })
    ).data,
    onSuccess: setPreview,
    onError: (e: unknown) => toastError("Не удалось проверить список", getErrorDetail(e)),
  })

  const bulkImport = useMutation({
    mutationFn: async () => (
      await api.post<ImportPreview>("/v1/admin/settings/email-domains/bulk", {
        raw_text: bulkText,
      })
    ).data,
    onSuccess: (result) => {
      setPreview(result)
      toastSuccess(`Добавлено доменов: ${result.new_count}`)
      void qc.invalidateQueries({ queryKey: ["admin-banned-domains"] })
    },
    onError: (e: unknown) => toastError("Не удалось импортировать список", getErrorDetail(e)),
  })

  const closeBulk = () => {
    setBulkOpen(false)
    setBulkText("")
    setPreview(null)
    bulkPreview.reset()
    bulkImport.reset()
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Заблокированные почтовые домены</CardTitle>
          <CardDescription>Регистрация с почтой на этих доменах отклоняется.</CardDescription>
        </div>
        {canEdit && (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setBulkOpen(true)}>
              Массовый импорт
            </Button>
            <Button size="sm" onClick={() => setAdding(true)}>
              <Plus className="size-4" /> Добавить
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
        {!isLoading && (data?.length ?? 0) === 0 && (
          <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
            <Ban className="size-6" />
            Заблокированных доменов нет.
          </div>
        )}
        {!isLoading && (data?.length ?? 0) > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Домен</TableHead>
                <TableHead>Причина</TableHead>
                <TableHead>Добавлен</TableHead>
                {canEdit && <TableHead className="text-right">Действия</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.map((d) => (
                <TableRow key={d.domain}>
                  <TableCell className="font-mono text-xs">{d.domain}</TableCell>
                  <TableCell className="text-muted-foreground">{d.reason ?? "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(d.created_at).toLocaleDateString()}
                  </TableCell>
                  {canEdit && (
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8 text-destructive"
                        onClick={() => remove.mutate(d.domain)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      <AddDomainDialog open={adding} onOpenChange={setAdding} />
      <Dialog open={bulkOpen} onOpenChange={(open) => open ? setBulkOpen(true) : closeBulk()}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Массовый импорт доменов</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Введите по одному домену на строку или CSV: <code>домен,причина</code>.
            Запись выполняется только после проверки списка.
          </p>
          <textarea
            value={bulkText}
            onChange={(event) => {
              setBulkText(event.target.value)
              setPreview(null)
            }}
            placeholder={"tempmail.com\nexample.org,временная почта"}
            className="min-h-40 w-full resize-y rounded-md border bg-background px-3 py-2 font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          {preview && (
            <div className="space-y-2 rounded-md border p-3 text-sm">
              <div className="flex flex-wrap gap-3">
                <span className="text-emerald-500">Новые: {preview.new_count}</span>
                <span className="text-muted-foreground">Уже есть: {preview.existing_count}</span>
                <span className="text-amber-500">Дубли: {preview.duplicate_count}</span>
                <span className="text-destructive">Ошибки: {preview.invalid_count}</span>
              </div>
              <div className="max-h-40 space-y-1 overflow-y-auto border-t pt-2">
                {preview.items.map((item) => (
                  <div key={`${item.line}-${item.value}`} className="flex gap-2 font-mono text-xs">
                    <span className="w-8 text-muted-foreground">{item.line}</span>
                    <span className="min-w-0 flex-1 truncate">{item.value}</span>
                    <span className={item.status === "new" ? "text-emerald-500" : item.status === "invalid" ? "text-destructive" : "text-muted-foreground"}>
                      {item.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={closeBulk}>Отмена</Button>
            <Button
              variant="outline"
              disabled={!bulkText.trim() || bulkPreview.isPending}
              onClick={() => bulkPreview.mutate()}
            >
              Проверить
            </Button>
            <Button
              disabled={!preview || preview.new_count === 0 || preview.invalid_count > 0 || bulkImport.isPending}
              onClick={() => bulkImport.mutate()}
            >
              Импортировать новые
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
