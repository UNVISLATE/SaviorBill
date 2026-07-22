import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { hasPerm, type PermNode } from "@/api/rbac.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { Badge } from "@/components/shadsnui/badge"
import { Checkbox } from "@/components/shadsnui/checkbox"
import { Input } from "@/components/shadsnui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
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

interface Role {
  id: number
  name: string
  title: string | null
  is_system: boolean
  perms: PermNode
}

/** Собрать вложенный perms-объект из списка плоских путей (только true-листья) —
 * зеркалит `security/rbac.py::perms_tree`, но строит дерево только по выбранным
 * правам, а не по всему каталогу. */
function buildPermsTree(paths: string[]): Record<string, unknown> {
  const tree: Record<string, unknown> = {}
  for (const path of paths) {
    const segs = path.split(".")
    let node = tree
    for (let i = 0; i < segs.length - 1; i++) {
      const seg = segs[i]
      if (typeof node[seg] !== "object" || node[seg] === null) node[seg] = {}
      node = node[seg] as Record<string, unknown>
    }
    node[segs[segs.length - 1]] = true
  }
  return tree
}

export function RolesPage() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<Role | null>(null)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [permFilter, setPermFilter] = useState("")

  const { data: roles, isLoading } = useQuery({
    queryKey: ["admin-roles"],
    queryFn: async () => (await api.get<Role[]>("/v1/admin/roles")).data,
  })

  const { data: catalog } = useQuery({
    queryKey: ["admin-perms-catalog"],
    queryFn: async () => (await api.get<{ flat: string[]; tree: unknown }>("/v1/admin/perms")).data,
  })

  const save = useMutation({
    mutationFn: async () => {
      if (!editing) return
      await api.patch(`/v1/admin/roles/${editing.id}`, {
        perms: buildPermsTree(Array.from(checked)),
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-roles"] })
      toastSuccess("Права роли обновлены")
      setEditing(null)
    },
    onError: () => toastError("Не удалось сохранить права роли"),
  })

  function openEdit(role: Role) {
    const flat = catalog?.flat ?? []
    setChecked(new Set(flat.filter((p) => hasPerm(role.perms, p))))
    setPermFilter("")
    setEditing(role)
  }

  const filteredPerms = useMemo(() => {
    const flat = catalog?.flat ?? []
    if (!permFilter.trim()) return flat
    const q = permFilter.trim().toLowerCase()
    return flat.filter((p) => p.toLowerCase().includes(q))
  }, [catalog, permFilter])

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Роли</h1>
        {roles && <span className="text-sm text-muted-foreground">Всего: {roles.length}</span>}
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Название</TableHead>
              <TableHead>Тип</TableHead>
              <TableHead>Прав</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                  Загрузка…
                </TableCell>
              </TableRow>
            )}
            {roles?.map((r) => (
              <TableRow key={r.id}>
                <TableCell>{r.id}</TableCell>
                <TableCell>
                  <span className="font-medium">{r.title ?? r.name}</span>
                  <span className="ml-1.5 text-xs text-muted-foreground">{r.name}</span>
                </TableCell>
                <TableCell>
                  {r.name === "owner" ? (
                    <Badge variant="outline">owner — неприкасаема</Badge>
                  ) : r.is_system ? (
                    <Badge variant="secondary">системная</Badge>
                  ) : (
                    <Badge variant="outline">кастомная</Badge>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {catalog ? catalog.flat.filter((p) => hasPerm(r.perms, p)).length : "—"}
                </TableCell>
                <TableCell>
                  {r.name !== "owner" && (
                    <Button size="sm" variant="outline" onClick={() => openEdit(r)}>
                      Права
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="max-h-[80vh] max-w-lg overflow-hidden">
          <DialogHeader>
            <DialogTitle>Права роли «{editing?.title ?? editing?.name}»</DialogTitle>
            <DialogDescription>
              Отметьте разрешения, доступные этой роли. Права наследуются по иерархии.
            </DialogDescription>
          </DialogHeader>
          <Input
            value={permFilter}
            onChange={(e) => setPermFilter(e.target.value)}
            placeholder="Фильтр прав…"
          />
          <div className="max-h-[45vh] space-y-1 overflow-y-auto pr-1">
            {filteredPerms.map((p) => (
              <label key={p} className="flex items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-muted/50">
                <Checkbox
                  checked={checked.has(p)}
                  onCheckedChange={(v) => {
                    setChecked((prev) => {
                      const next = new Set(prev)
                      if (v) next.add(p)
                      else next.delete(p)
                      return next
                    })
                  }}
                />
                <span className="font-mono text-xs">{p}</span>
              </label>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>
              Отмена
            </Button>
            <Button onClick={() => save.mutate()} disabled={save.isPending}>
              Сохранить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
