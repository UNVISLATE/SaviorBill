import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { MoreHorizontal, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { useProfileDialog } from "@/hooks/use-profile-dialog"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/shadsnui/dropdown-menu"
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
import { toastError, toastSuccess } from "@/lib/toast"

interface User {
  id: number
  login: string
  email: string | null
  is_active: boolean
  is_verified: boolean
  role_id: number | null
  balance: string
  bonus_balance: string
  created_at: string
  last_login: string | null
}

interface Role {
  id: number
  key: string
  name: string
}

interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

interface UserStats {
  total: number
  registered_1d: number
  registered_7d: number
  registered_30d: number
  registered_90d: number
}

function StatCard({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-lg border bg-card px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-semibold">{value ?? "—"}</div>
    </div>
  )
}

function DeleteUserDialog({
  user,
  open,
  onOpenChange,
}: {
  user: User
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const [confirmText, setConfirmText] = useState("")
  const qc = useQueryClient()

  const del = useMutation({
    mutationFn: async () => api.delete(`/v1/admin/users/${user.id}`),
    onSuccess: () => {
      toastSuccess(`Пользователь «${user.login}» удалён`)
      onOpenChange(false)
      setConfirmText("")
      void qc.invalidateQueries({ queryKey: ["admin-users"] })
      void qc.invalidateQueries({ queryKey: ["admin-users-stats"] })
    },
    onError: (e: unknown) => {
      const detail =
        e && typeof e === "object" && "response" in e
          ? // @ts-expect-error — axios error shape
            e.response?.data?.detail
          : undefined
      toastError("Не удалось удалить пользователя", typeof detail === "string" ? detail : undefined)
    },
  })

  return (
    <AlertDialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) setConfirmText("") }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Удалить пользователя?</AlertDialogTitle>
          <AlertDialogDescription>
            Действие необратимо: удалятся услуги, платежи, OAuth-привязки и
            активации промокодов этого пользователя. Введите{" "}
            <code className="rounded bg-muted px-1 py-0.5 select-all">{user.login}</code>{" "}
            для подтверждения.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <Input
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          placeholder="введите логин"
          autoFocus
        />
        <AlertDialogFooter>
          <AlertDialogCancel>Отмена</AlertDialogCancel>
          <AlertDialogAction
            disabled={confirmText !== user.login || del.isPending}
            onClick={() => del.mutate()}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            Удалить
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export function UsersPage() {
  const { openUserProfile } = useProfileDialog()
  const { can } = useAuth()
  const table = useDataTableQuery()
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null)
  const canDelete = can("users.admin.delete")

  const { data: roles } = useQuery({
    queryKey: ["admin-roles-lookup"],
    queryFn: async () => (await api.get<Role[]>("/v1/admin/roles")).data,
    staleTime: 5 * 60_000,
  })
  const roleByI = (id: number | null) => roles?.find((r) => r.id === id)
  const isOwnerRow = (u: User) => roleByI(u.role_id)?.key === "owner"

  const { data: stats } = useQuery({
    queryKey: ["admin-users-stats"],
    queryFn: async () => (await api.get<UserStats>("/v1/admin/users/stats")).data,
  })

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-users", table.limit, table.offset, table.sort, table.search],
    queryFn: async () =>
      (
        await api.get<Page<User>>("/v1/admin/users", {
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

  const columns: DataTableColumn<User>[] = [
    { key: "id", header: "ID", render: (u) => <span className="font-mono text-xs">{u.id}</span> },
    { key: "login", header: "Логин", render: (u) => <span className="font-medium">{u.login}</span> },
    { key: "email", header: "Email", render: (u) => u.email ?? "—" },
    {
      header: "Роль",
      render: (u) => {
        const r = roleByI(u.role_id)
        return r ? (
          <Badge variant={r.key === "owner" ? "default" : "outline"}>{r.name}</Badge>
        ) : (
          "—"
        )
      },
    },
    {
      header: "Статус",
      render: (u) => (
        <Badge variant={u.is_active ? "outline" : "destructive"}>
          {u.is_active ? "активен" : "забанен"}
        </Badge>
      ),
    },
    { key: "balance", header: "Баланс", render: (u) => u.balance },
    {
      key: "created_at",
      header: "Регистрация",
      render: (u) => new Date(u.created_at).toLocaleDateString(),
    },
    ...(canDelete
      ? [
          {
            header: "",
            render: (u: User) =>
              isOwnerRow(u) ? null : (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <MoreHorizontal className="size-4" />
                      </Button>
                    }
                  />
                  <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
                    <DropdownMenuItem
                      variant="destructive"
                      onClick={() => setDeleteTarget(u)}
                    >
                      <Trash2 className="size-4" /> Удалить
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ),
          } satisfies DataTableColumn<User>,
        ]
      : []),
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Пользователи</h1>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <StatCard label="Всего" value={stats?.total} />
        <StatCard label="За 1 день" value={stats?.registered_1d} />
        <StatCard label="За 7 дней" value={stats?.registered_7d} />
        <StatCard label="За 30 дней" value={stats?.registered_30d} />
        <StatCard label="За 90 дней" value={stats?.registered_90d} />
      </div>

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        total={data?.total ?? 0}
        isLoading={isLoading}
        isError={isError}
        getRowId={(u) => u.id}
        onRowClick={(u) => openUserProfile(u.id)}
        sort={table.sort}
        onToggleSort={table.toggleSort}
        searchValue={table.searchInput}
        onSearchChange={table.setSearchInput}
        searchPlaceholder="Поиск по логину/email…"
        limit={table.limit}
        offset={table.offset}
        hasMore={data?.has_more ?? false}
        onLimitChange={table.changeLimit}
        onOffsetChange={table.setOffset}
      />

      {deleteTarget && (
        <DeleteUserDialog
          user={deleteTarget}
          open={!!deleteTarget}
          onOpenChange={(v) => !v && setDeleteTarget(null)}
        />
      )}
    </div>
  )
}
