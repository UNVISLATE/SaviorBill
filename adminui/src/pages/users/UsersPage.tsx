import { useQuery } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { useProfileDialog } from "@/hooks/use-profile-dialog"
import { useDataTableQuery } from "@/hooks/use-data-table"
import { DataTable, type DataTableColumn } from "@/components/data-table/DataTable"
import { Badge } from "@/components/shadsnui/badge"

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

interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

const columns: DataTableColumn<User>[] = [
  { key: "id", header: "ID", render: (u) => u.id },
  { key: "login", header: "Логин", render: (u) => <span className="font-medium">{u.login}</span> },
  { key: "email", header: "Email", render: (u) => u.email ?? "—" },
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
]

export function UsersPage() {
  const { openUserProfile } = useProfileDialog()
  const table = useDataTableQuery()

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

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Пользователи</h1>
        {data && (
          <span className="text-sm text-muted-foreground">Всего: {data.total}</span>
        )}
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
    </div>
  )
}
