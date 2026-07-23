import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronLeft, ChevronRight } from "lucide-react"

import { api } from "@/api/api.ts"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { toastError, toastSuccess } from "@/lib/toast"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Textarea } from "@/components/shadsnui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
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
  group: string
  desc: string | null
  created_at: string
  updated_at: string
}

interface SettingsGroup {
  name: string
  count: number
}

interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

const NEW_GROUP = "__new__"

function GroupsList({ onOpen }: { onOpen: (group: string) => void }) {
  const { data: groups, isLoading } = useQuery({
    queryKey: ["admin-settings-groups"],
    queryFn: async () => (await api.get<SettingsGroup[]>("/v1/admin/settings/raw/groups")).data,
  })

  return (
    <div className="rounded-lg border">
      {isLoading && (
        <div className="py-8 text-center text-sm text-muted-foreground">Загрузка…</div>
      )}
      <div className="divide-y">
        {groups?.map((g) => (
          <button
            key={g.name}
            onClick={() => onOpen(g.name)}
            className="flex w-full items-center justify-between px-4 py-3 text-left text-sm hover:bg-muted/50"
          >
            <span className="font-mono">{g.name}</span>
            <span className="flex items-center gap-2 text-muted-foreground">
              {g.count} {g.count === 1 ? "ключ" : "ключей"}
              <ChevronRight className="size-4" />
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

function GroupTable({ group, onBack }: { group: string; onBack: () => void }) {
  const qc = useQueryClient()
  const table = useDataTableQuery()
  const [editing, setEditing] = useState<SettingRow | null>(null)
  const [creating, setCreating] = useState(false)
  const [newKeySuffix, setNewKeySuffix] = useState("")
  const [draftValue, setDraftValue] = useState("")
  const [deleting, setDeleting] = useState<SettingRow | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-settings-raw", group, table.limit, table.offset, table.sort, table.search],
    queryFn: async () =>
      (
        await api.get<Page<SettingRow>>("/v1/admin/settings/raw", {
          params: {
            group,
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
      qc.invalidateQueries({ queryKey: ["admin-settings-groups"] })
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
      qc.invalidateQueries({ queryKey: ["admin-settings-groups"] })
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
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={onBack}>
            <ChevronLeft className="size-4" /> Назад
          </Button>
          <h2 className="text-lg font-semibold font-mono">{group}</h2>
        </div>
        <Button
          size="sm"
          onClick={() => {
            setNewKeySuffix("")
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
            <DialogTitle>Новая настройка в «{group}»</DialogTitle>
          </DialogHeader>
          <div className="flex items-center gap-1 font-mono text-sm">
            <span className="text-muted-foreground">{group}.</span>
            <Input
              value={newKeySuffix}
              onChange={(e) => setNewKeySuffix(e.target.value)}
              placeholder="остаток.ключа"
              className="font-mono text-xs"
            />
          </div>
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
              onClick={() =>
                newKeySuffix.trim() &&
                upsert.mutate({ key: `${group}.${newKeySuffix.trim()}`, value: draftValue })
              }
              disabled={upsert.isPending || !newKeySuffix.trim()}
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

function NewGroupDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onCreated: (group: string) => void
}) {
  const qc = useQueryClient()
  const [groupChoice, setGroupChoice] = useState<string>("")
  const [customGroup, setCustomGroup] = useState("")
  const [keySuffix, setKeySuffix] = useState("")
  const [draftValue, setDraftValue] = useState("")
  const { data: groups } = useQuery({
    queryKey: ["admin-settings-groups"],
    queryFn: async () => (await api.get<SettingsGroup[]>("/v1/admin/settings/raw/groups")).data,
  })

  const finalGroup = groupChoice === NEW_GROUP ? customGroup.trim() : groupChoice

  const create = useMutation({
    mutationFn: async () =>
      api.put(`/v1/admin/settings/raw/${encodeURIComponent(`${finalGroup}.${keySuffix.trim()}`)}`, {
        value: draftValue,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings-groups"] })
      toastSuccess("Настройка создана")
      onOpenChange(false)
      onCreated(finalGroup)
    },
    onError: () => toastError("Не удалось создать настройку"),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новая настройка</DialogTitle>
        </DialogHeader>
        <div className="space-y-1">
          <div className="text-sm text-muted-foreground">Группа (префикс)</div>
          <Select value={groupChoice} onValueChange={(v) => setGroupChoice(v ?? "")}>
            <SelectTrigger>
              <SelectValue placeholder="Выберите группу…" />
            </SelectTrigger>
            <SelectContent>
              {groups?.map((g) => (
                <SelectItem key={g.name} value={g.name}>
                  {g.name}
                </SelectItem>
              ))}
              <SelectItem value={NEW_GROUP}>+ новая группа…</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {groupChoice === NEW_GROUP && (
          <Input
            value={customGroup}
            onChange={(e) => setCustomGroup(e.target.value)}
            placeholder="название новой группы"
            className="font-mono text-xs"
          />
        )}
        <div className="flex items-center gap-1 font-mono text-sm">
          <span className="text-muted-foreground">{finalGroup || "группа"}.</span>
          <Input
            value={keySuffix}
            onChange={(e) => setKeySuffix(e.target.value)}
            placeholder="остаток.ключа"
            className="font-mono text-xs"
          />
        </div>
        <Textarea
          value={draftValue}
          onChange={(e) => setDraftValue(e.target.value)}
          rows={6}
          placeholder="значение"
          className="font-mono text-xs"
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            disabled={!finalGroup || !keySuffix.trim() || create.isPending}
            onClick={() => create.mutate()}
          >
            Создать
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function RawSettingsEditor() {
  const [openGroup, setOpenGroup] = useState<string | null>(null)
  const [creatingGroup, setCreatingGroup] = useState(false)

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-semibold">Raw-редактирование настроек</h2>
          <p className="text-sm text-muted-foreground">
            Прямой доступ к таблице settings (key-value), сгруппированный по префиксам.
            Секретные и системные ключи скрыты от редактирования — ими управляют
            профильные разделы админки.
          </p>
        </div>
        {!openGroup && (
          <Button size="sm" onClick={() => setCreatingGroup(true)}>
            Новая настройка
          </Button>
        )}
      </div>

      {openGroup ? (
        <GroupTable group={openGroup} onBack={() => setOpenGroup(null)} />
      ) : (
        <GroupsList onOpen={setOpenGroup} />
      )}

      <NewGroupDialog
        open={creatingGroup}
        onOpenChange={setCreatingGroup}
        onCreated={setOpenGroup}
      />
    </div>
  )
}
