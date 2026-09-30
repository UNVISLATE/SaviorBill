import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FileUp, Plus, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { AnimatedLoader } from "@/components/animbits/AnimatedLoader"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
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
import { toastError, toastSuccess } from "@/lib/toast"

interface BannedDomain {
  domain: string
  reason: string | null
  created_at: string
}

interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
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

const PREVIEW_ITEM_LIMIT = 100

/** Заблокированные для регистрации email-домены — попытка зарегистрироваться
 * с почтой на таком домене отклоняется на бэкенде (защита от временной
 * почты/спама). Список маленький — без пагинации, простая таблица. */
export function BannedDomainsSettings() {
  const { can } = useAuth()
  const [bulkOpen, setBulkOpen] = useState(false)
  const [bulkText, setBulkText] = useState("")
  const [bulkUrl, setBulkUrl] = useState("")
  const [sourceMode, setSourceMode] = useState<"text" | "url">("text")
  const [bulkReason, setBulkReason] = useState("")
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const canEdit = can("settings.email_domains.edit")
  const qc = useQueryClient()
  const table = useDataTableQuery()

  const { data, isLoading } = useQuery({
    queryKey: ["admin-banned-domains", table.limit, table.offset, table.search, table.sort],
    queryFn: async () => (
      await api.get<Page<BannedDomain>>("/v1/admin/settings/email-domains", {
        params: {
          limit: table.limit,
          offset: table.offset,
          q: table.search || undefined,
          sort: table.sort || undefined,
        },
      })
    ).data,
    placeholderData: (previous) => previous,
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
        raw_text: sourceMode === "text" ? bulkText : "",
        source_url: sourceMode === "url" ? bulkUrl : null,
        reason: bulkReason || null,
      })
    ).data,
    onSuccess: setPreview,
    onError: (e: unknown) => toastError("Не удалось проверить список", getErrorDetail(e)),
  })
  const previewMutateRef = useRef(bulkPreview.mutate)
  const previewResetRef = useRef(bulkPreview.reset)

  const bulkImport = useMutation({
    mutationFn: async () => (
      await api.post<ImportPreview>("/v1/admin/settings/email-domains/bulk", {
        raw_text: sourceMode === "text" ? bulkText : "",
        source_url: sourceMode === "url" ? bulkUrl : null,
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
  const bulkBusy = bulkPreview.isPending || bulkImport.isPending

  const closeBulk = () => {
    setBulkOpen(false)
    setBulkText("")
    setBulkUrl("")
    setSourceMode("text")
    setBulkReason("")
    setPreview(null)
    bulkPreview.reset()
    bulkImport.reset()
  }

  useEffect(() => {
    if (!bulkOpen) return
    if (sourceMode !== "text" || !bulkText.trim()) {
      previewResetRef.current()
      return
    }
    const timer = window.setTimeout(() => previewMutateRef.current(), 350)
    return () => window.clearTimeout(timer)
  }, [bulkOpen, bulkText, sourceMode])

  async function loadFile(file: File) {
    if (!file.name.toLowerCase().endsWith(".txt") && !file.name.toLowerCase().endsWith(".csv")) {
      toastError("Неподдерживаемый файл", "Выберите файл .txt или .csv")
      return
    }
    try {
      setPreview(null)
      setBulkUrl("")
      setSourceMode("text")
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
        <DataTable
          columns={[
            { key: "domain", header: "Домен", render: (d) => <span className="font-mono text-xs">{d.domain}</span> },
            { key: "reason", header: "Причина", render: (d) => <span className="text-muted-foreground">{d.reason ?? "—"}</span> },
            {
              key: "created_at",
              header: "Добавлен",
              render: (d) => <span className="text-xs text-muted-foreground">{new Date(d.created_at).toLocaleDateString()}</span>,
            },
            ...(canEdit
              ? [{
                  header: <span className="block text-right">Действия</span>,
                  render: (d: BannedDomain) => (
                    <div className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-7 text-destructive"
                        onClick={() => remove.mutate(d.domain)}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  ),
                } satisfies DataTableColumn<BannedDomain>]
              : []),
          ] satisfies DataTableColumn<BannedDomain>[]}
          data={data?.items ?? []}
          total={data?.total ?? 0}
          isLoading={isLoading}
          getRowId={(d) => d.domain}
          sort={table.sort}
          onToggleSort={table.toggleSort}
          searchValue={table.searchInput}
          onSearchChange={table.setSearchInput}
          searchPlaceholder="Поиск по домену или причине…"
          limit={table.limit}
          offset={table.offset}
          hasMore={data?.has_more ?? false}
          onLimitChange={table.changeLimit}
          onOffsetChange={table.setOffset}
          emptyMessage="Заблокированные домены не найдены"
          emptyHint={table.search ? "Попробуйте изменить поисковый запрос." : "Здесь появятся добавленные домены."}
        />
      </CardContent>
      <Dialog open={bulkOpen} onOpenChange={(open) => {
        if (bulkBusy) return
        if (open) setBulkOpen(true)
        else closeBulk()
      }}>
        <DialogContent
          className="relative flex max-h-[85vh] w-full max-w-[calc(100%-2rem)] flex-col overflow-hidden p-6 sm:max-w-[760px]"
          showCloseButton={!bulkBusy}
          aria-busy={bulkBusy}
        >
          {bulkBusy && (
            <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-background/75 backdrop-blur-[2px]">
              <AnimatedLoader />
            </div>
          )}
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
            <DialogHeader>
              <DialogTitle>Добавить заблокированные домены</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
            Добавьте один домен или список: по одному домену на строку либо CSV в формате{" "}
            <code>домен,причина</code>.
            </p>
            <div className="flex gap-1 rounded-md bg-muted p-1">
            <Button
              type="button"
              size="sm"
              variant={sourceMode === "text" ? "secondary" : "ghost"}
              className="flex-1"
              disabled={bulkBusy}
              onClick={() => {
                setSourceMode("text")
                setPreview(null)
              }}
            >
              Текст / файл
            </Button>
            <Button
              type="button"
              size="sm"
              variant={sourceMode === "url" ? "secondary" : "ghost"}
              className="flex-1"
              disabled={bulkBusy}
              onClick={() => {
                setSourceMode("url")
                setPreview(null)
              }}
            >
              Ссылка
            </Button>
            </div>
            {sourceMode === "text" ? (
            <>
              <div className="space-y-1.5">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".txt,.csv,text/plain,text/csv"
                  className="hidden"
                  disabled={bulkBusy}
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file) void loadFile(file)
                    event.target.value = ""
                  }}
                />
                <button
                  type="button"
                  disabled={bulkBusy}
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
                disabled={bulkBusy}
                onChange={(event) => {
                  setPreview(null)
                  setBulkText(event.target.value)
                }}
                placeholder={"tempmail.com\nexample.org,временная почта"}
                className="min-h-40 max-h-[300px] w-full resize-y overflow-y-auto rounded-md border bg-background px-3 py-2 font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </>
            ) : (
              <div className="space-y-2">
              <Label>Ссылка на документ GitHub</Label>
                <Input
                  className="min-w-0"
                value={bulkUrl}
                disabled={bulkBusy}
                onChange={(event) => {
                  setPreview(null)
                  setBulkUrl(event.target.value)
                }}
                placeholder="https://raw.githubusercontent.com/.../domains.txt"
                type="url"
              />
              <Button
                type="button"
                variant="outline"
                className="w-full"
                disabled={!bulkUrl.trim() || bulkBusy}
                onClick={() => bulkPreview.mutate()}
              >
                Загрузить и проверить ссылку
              </Button>
              <p className="text-xs text-muted-foreground">
                Разрешён только raw.githubusercontent.com. Запрос выполняется только по этой кнопке.
              </p>
              </div>
            )}
            <div className="space-y-1">
            <Label>Общая причина (опционально)</Label>
            <Input disabled={bulkBusy} value={bulkReason} onChange={(event) => setBulkReason(event.target.value)} placeholder="временная почта" />
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
            {preview && preview.invalid_count > 0 && (
              <p className="text-xs text-amber-500">
                Некорректные строки будут пропущены и не добавятся. Остальные домены можно импортировать.
              </p>
            )}
            {preview && (
            <div className="min-h-0 w-full space-y-2 rounded-md border p-3 text-sm">
              <div className="flex flex-wrap gap-3">
                <span className="text-emerald-500">Новые: {preview.new_count}</span>
                <span className="text-muted-foreground">Уже есть: {preview.existing_count}</span>
                <span className="text-amber-500">Дубли: {preview.duplicate_count}</span>
                <span className="text-destructive">Ошибки: {preview.invalid_count}</span>
              </div>
              <div className="max-h-[250px] w-full space-y-1 overflow-y-auto border-t pt-2">
                {preview.items.slice(0, PREVIEW_ITEM_LIMIT).map((item) => (
                  <div key={`${item.line}-${item.value}`} className="flex gap-2 font-mono text-xs">
                    <span className="w-8 text-muted-foreground">{item.line}</span>
                    <span className="min-w-0 flex-1 truncate">{item.value}</span>
                    <span className={item.status === "new" ? "text-emerald-500" : item.status === "invalid" ? "text-destructive" : "text-muted-foreground"}>
                      {item.status}
                    </span>
                  </div>
                ))}
                {preview.items.length > PREVIEW_ITEM_LIMIT && (
                  <div className="border-t pt-2 text-xs text-muted-foreground">
                    И ещё {preview.items.length - PREVIEW_ITEM_LIMIT} элементов…
                  </div>
                )}
              </div>
            </div>
            )}
          </div>
          <DialogFooter className="-mx-6 -mb-6 flex-shrink-0 flex-wrap pt-4">
            <Button disabled={bulkBusy} variant="outline" className="min-w-24" onClick={closeBulk}>Отмена</Button>
            <Button
              className="min-w-32"
              disabled={!preview || preview.new_count === 0 || bulkBusy}
              onClick={() => bulkImport.mutate()}
            >
              {preview?.invalid_count ? "Импортировать валидные" : "Импортировать"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
