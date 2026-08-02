import { useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/shadsnui/dialog"
import { Input } from "@/components/shadsnui/input"
import { Badge } from "@/components/shadsnui/badge"

interface UserItem {
  id: number
  login: string
  email: string | null
}

interface Page<T> {
  items: T[]
}

/** Диалог поиска пользователя по логину/email — используется там, где нужен
 * account_id (выдача услуги вручную и т.п.), чтобы не заставлять админа
 * искать ID на отдельной странице пользователей. */
export function UserPickerDialog({
  open,
  onOpenChange,
  onSelect,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onSelect: (user: UserItem) => void
}) {
  const [q, setQ] = useState("")

  const { data, isLoading } = useQuery({
    queryKey: ["user-picker", q],
    queryFn: async () =>
      (await api.get<Page<UserItem>>("/v1/admin/users", { params: { limit: 20, q: q || undefined } })).data.items,
    enabled: open && q.length > 0,
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Найти пользователя</DialogTitle>
        </DialogHeader>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Логин или email…" autoFocus />
        <div className="max-h-72 space-y-1 overflow-y-auto">
          {q.length === 0 && <p className="py-4 text-center text-sm text-muted-foreground">Начните вводить логин</p>}
          {isLoading && <p className="py-4 text-center text-sm text-muted-foreground">Поиск…</p>}
          {q.length > 0 && !isLoading && (data?.length ?? 0) === 0 && (
            <p className="py-4 text-center text-sm text-muted-foreground">Никого не найдено</p>
          )}
          {data?.map((u) => (
            <button
              key={u.id}
              type="button"
              onClick={() => {
                onSelect(u)
                onOpenChange(false)
              }}
              className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
            >
              <span className="font-medium">{u.login}</span>
              <Badge variant="outline" className="font-mono text-[10px]">
                #{u.id}
              </Badge>
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
