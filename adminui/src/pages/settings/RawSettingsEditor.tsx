import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { toastError, toastSuccess } from "@/lib/toast"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Textarea } from "@/components/shadsnui/textarea"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/shadsnui/alert-dialog"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"

interface SettingRow {
  key: string
  value: string | null
  is_secret: boolean
  editable: boolean
  group: string | null
  desc: string | null
  created_at: string
  updated_at: string
}

interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export function RawSettingsEditor() {
  const qc = useQueryClient()
  const table = useDataTableQuery()
  const [editing, setEditing] = useState<SettingRow | null>(null)
  const [creating, setCreating] = useState(false)
  const [newKey, setNewKey] = useState("")
  const [draftValue, setDraftValue] = useState("")
  const [deleting, setDeleting] = useState<SettingRow | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-settings-raw", table.limit, table.offset, table.sort, table.search],
    queryFn: async () =>
      (
        await api.get<Page<SettingRow>>("/v1/admin/settings/raw", {
          params: {
            limit: table.limit,
            offset: table.offset,
            sort: table.sort ?? undefined,
            q: table.search || undefined,
          },
        })
      ).data,
    placeholderData: (prev) => prev,
  })

  const upsert = useMutation({
    mutationFn: async (vars: { key: string; value: string }) => {
      await api.put(`/v1/admin/settings/raw/${encodeURIComponent(vars.key)}`, { value: vars.value })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings-raw"] })
      toastSuccess("Настройка сохранена")
      setEditing(null)
      setCreating(false)
    },
    onError: () => toastError("Не удалось сохранить настройку"),
  })

  const del = useMutation({
    mutationFn: async (key: string) => {
      await api.delete(`/v1/admin/settings/raw/${encodeURIComponent(key)}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings-raw"] })
      toastSuccess("Настройка удалена")
      setDeleting(null)
    },
    onError: () => toastError("Не удалось удалить настройку — возможно, она защищена"),
  })

  const columns: DataTableColumn<SettingRow>[] = [
    { key: "key", header: "Ключ", render: (r) => <span className="font-mono text-xs">{r.key}</span> },
    {
      header: "Значение",
      render: (r) =>
        r.is_secret ? (
          <Badge variant="secondary">секрет — скрыто</Badge>
        ) : (
          <span className="max-w-xs truncate font-mono text-xs text-muted-foreground">
            {r.value ?? "—"}
          </span>
        ),
    },
    { header: "Группа", render: (r) => r.group ?? "—" },
    {
      key: "updated_at",
      header: "Обновлено",
      render: (r) => new Date(r.updated_at).toLocaleString(),
    },
    {
      header: "",
      render: (r) => (
        <div className="flex justify-end gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!r.editable}
            onClick={() => {
              setDraftValue(r.value ?? "")
              setEditing(r)
            }}
          >
            Изменить
          </Button>
          <Button size="sm" variant="destructive" disabled={!r.editable} onClick={() => setDeleting(r)}>
            Удалить
          </Button>
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-semibold">Raw-редактирование настроек</h2>
          <p className="text-sm text-muted-foreground">
            Прямой доступ к таблице settings (key-value). Секретные и системные ключи
            скрыты от редактирования — ими управляют профильные разделы админки.
          </p>
        </div>
        <Button
          size="sm"
          onClick={() => {
            setNewKey("")
            setDraftValue("")
            setCreating(true)
          }}
        >
          Новая настройка
        </Button>
      </div>

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        total={data?.total ?? 0}
        isLoading={isLoading}
        isError={isError}
        getRowId={(r) => r.key}
        sort={table.sort}
        onToggleSort={table.toggleSort}
        searchValue={table.searchInput}
        onSearchChange={table.setSearchInput}
        searchPlaceholder="Поиск по ключу…"
        limit={table.limit}
        offset={table.offset}
        hasMore={data?.has_more ?? false}
        onLimitChange={table.changeLimit}
        onOffsetChange={table.setOffset}
      />

      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Изменить «{editing?.key}»</DialogTitle>
          </DialogHeader>
          <Textarea
            value={draftValue}
            onChange={(e) => setDraftValue(e.target.value)}
            rows={6}
            className="font-mono text-xs"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>
              Отмена
            </Button>
            <Button
              onClick={() => editing && upsert.mutate({ key: editing.key, value: draftValue })}
              disabled={upsert.isPending}
            >
              Сохранить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Новая настройка</DialogTitle>
          </DialogHeader>
          <Input value={newKey} onChange={(e) => setNewKey(e.target.value)} placeholder="ключ.в.точечной.нотации" />
          <Textarea
            value={draftValue}
            onChange={(e) => setDraftValue(e.target.value)}
            rows={6}
            placeholder="значение"
            className="font-mono text-xs"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreating(false)}>
              Отмена
            </Button>
            <Button
              onClick={() => newKey.trim() && upsert.mutate({ key: newKey.trim(), value: draftValue })}
              disabled={upsert.isPending || !newKey.trim()}
            >
              Создать
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить «{deleting?.key}»?</AlertDialogTitle>
            <AlertDialogDescription>
              Действие нельзя отменить. Значение будет удалено из таблицы settings.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={del.isPending}
              onClick={() => deleting && del.mutate(deleting.key)}
            >
              Удалить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
