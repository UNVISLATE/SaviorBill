import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Ban, FileUp, Plus, Trash2 } from "lucide-react"

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

/** Заблокированные для регистрации email-домены — попытка зарегистрироваться
 * с почтой на таком домене отклоняется на бэкенде (защита от временной
 * почты/спама). Список маленький — без пагинации, простая таблица. */
export function BannedDomainsSettings() {
  const { can } = useAuth()
  const [bulkOpen, setBulkOpen] = useState(false)
  const [bulkText, setBulkText] = useState("")
  const [bulkUrl, setBulkUrl] = useState("")
  const [bulkReason, setBulkReason] = useState("")
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
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
        raw_text: bulkUrl ? "" : bulkText,
        source_url: bulkUrl || null,
        reason: bulkReason || null,
      })
    ).data,
    onSuccess: setPreview,
    onError: (e: unknown) => toastError("Не удалось проверить список", getErrorDetail(e)),
  })

  const bulkImport = useMutation({
    mutationFn: async () => (
      await api.post<ImportPreview>("/v1/admin/settings/email-domains/bulk", {
        raw_text: bulkUrl ? "" : bulkText,
        source_url: bulkUrl || null,
        reason: bulkReason || null,
      })
    ).data,
    onSuccess: (result) => {
      toastSuccess(`Добавлено доменов: ${result.new_count}`)
      void qc.invalidateQueries({ queryKey: ["admin-banned-domains"] })
      closeBulk()
    },
    onError: (e: unknown) => toastError("Не удалось импортировать список", getErrorDetail(e)),
  })

  const closeBulk = () => {
    setBulkOpen(false)
    setBulkText("")
    setBulkUrl("")
    setBulkReason("")
    setPreview(null)
    bulkPreview.reset()
    bulkImport.reset()
  }

  useEffect(() => {
    if (!bulkOpen) return
    if (!bulkText.trim() && !bulkUrl.trim()) {
      bulkPreview.reset()
      return
    }
    const timer = window.setTimeout(() => bulkPreview.mutate(), 350)
    return () => window.clearTimeout(timer)
  }, [bulkOpen, bulkText, bulkUrl, bulkPreview])

  async function loadFile(file: File) {
    if (!file.name.toLowerCase().endsWith(".txt") && !file.name.toLowerCase().endsWith(".csv")) {
      toastError("Неподдерживаемый файл", "Выберите файл .txt или .csv")
      return
    }
    try {
      setPreview(null)
      setBulkUrl("")
      setBulkText(await file.text())
    } catch (error) {
      toastError("Не удалось прочитать файл", getErrorDetail(error))
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Заблокированные почтовые домены</CardTitle>
          <CardDescription>Регистрация с почтой на этих доменах отклоняется.</CardDescription>
        </div>
        {canEdit && (
          <Button size="sm" onClick={() => setBulkOpen(true)}>
            <Plus className="size-4" /> Добавить домены
          </Button>
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
      <Dialog open={bulkOpen} onOpenChange={(open) => open ? setBulkOpen(true) : closeBulk()}>
        <DialogContent className="w-full max-w-[600px] p-6">
          <DialogHeader>
            <DialogTitle>Добавить заблокированные домены</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Добавьте один домен или список: по одному домену на строку либо CSV в формате{" "}
            <code>домен,причина</code>.
          </p>
          <div className="space-y-1">
            <Label>Или ссылка на .txt / .csv</Label>
            <Input
              value={bulkUrl}
              onChange={(event) => {
                setPreview(null)
                setBulkUrl(event.target.value)
                if (event.target.value) setBulkText("")
              }}
              placeholder="https://raw.githubusercontent.com/.../domains.txt"
              type="url"
            />
          </div>
          <div className="space-y-1.5">
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.csv,text/plain,text/csv"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) void loadFile(file)
                event.target.value = ""
              }}
            />
            <button
              type="button"
              className="flex w-full items-center justify-center gap-2 rounded-md border border-dashed px-3 py-3 text-sm text-muted-foreground transition-colors hover:border-primary hover:bg-muted/40 hover:text-foreground"
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault()
                const file = event.dataTransfer.files[0]
                if (file) void loadFile(file)
              }}
            >
              <FileUp className="size-4" />
              Загрузить .csv / .txt или перетащить файл
            </button>
          </div>
          <textarea
            value={bulkText}
            onChange={(event) => {
              setPreview(null)
              setBulkUrl("")
              setBulkText(event.target.value)
            }}
            placeholder={"tempmail.com\nexample.org,временная почта"}
            className="min-h-40 w-full resize-y rounded-md border bg-background px-3 py-2 font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <div className="space-y-1">
            <Label>Общая причина (опционально)</Label>
            <Input value={bulkReason} onChange={(event) => setBulkReason(event.target.value)} placeholder="временная почта" />
          </div>
          <div className="min-h-5 text-sm">
            {bulkPreview.isPending && <span className="text-muted-foreground">Проверяем список…</span>}
            {!bulkPreview.isPending && preview && (
              <span className="text-muted-foreground">
                Готово к импорту: <strong className="text-emerald-500">{preview.new_count}</strong>
                {" · "}Дубликаты: {preview.duplicate_count + preview.existing_count}
                {" · "}Ошибки: <strong className={preview.invalid_count ? "text-destructive" : "text-emerald-500"}>{preview.invalid_count}</strong>
              </span>
            )}
          </div>
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
          <DialogFooter className="-mx-6 -mb-6">
            <Button variant="outline" onClick={closeBulk}>Отмена</Button>
            <Button
              disabled={!preview || preview.new_count === 0 || preview.invalid_count > 0 || bulkImport.isPending}
              onClick={() => bulkImport.mutate()}
            >
              Импортировать
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
