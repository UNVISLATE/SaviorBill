import { useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { useProfileDialog } from "@/hooks/use-profile-dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/shadsnui/table"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Spinner } from "@/components/shadsnui/spinner"

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

const PAGE_SIZE = 25

export function UsersPage() {
  const [offset, setOffset] = useState(0)
  const { openUserProfile } = useProfileDialog()

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-users", offset],
    queryFn: async () =>
      (
        await api.get<Page<User>>("/v1/admin/users", {
          params: { limit: PAGE_SIZE, offset },
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

      {isLoading && <Spinner />}
      {isError && (
        <p className="text-sm text-destructive">Не удалось загрузить список.</p>
      )}

      {data && (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Логин</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Баланс</TableHead>
                <TableHead>Регистрация</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((u) => (
                <TableRow
                  key={u.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => openUserProfile(u.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") openUserProfile(u.id)
                  }}
                  className="cursor-pointer"
                >
                  <TableCell>{u.id}</TableCell>
                  <TableCell className="font-medium">{u.login}</TableCell>
                  <TableCell>{u.email ?? "—"}</TableCell>
                  <TableCell>
                    <Badge variant={u.is_active ? "outline" : "destructive"}>
                      {u.is_active ? "активен" : "забанен"}
                    </Badge>
                  </TableCell>
                  <TableCell>{u.balance}</TableCell>
                  <TableCell>{new Date(u.created_at).toLocaleDateString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            >
              Назад
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!data.has_more}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
            >
              Далее
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
