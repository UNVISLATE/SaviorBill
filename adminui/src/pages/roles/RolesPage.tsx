import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronRight, Minus, Trash2 } from "lucide-react"

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
  key: string | null
  title: string | null
  is_system: boolean
  is_protected: boolean
  admin_login_allowed: boolean
  allow_login: boolean
  perms: PermNode
}

type PermTree = Record<string, PermTree | true>

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

function treePaths(tree: PermTree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return value === true || Object.keys(value).length === 0
      ? [path]
      : treePaths(value, path)
  })
}

export function RolesPage() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<Role | null>(null)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [permFilter, setPermFilter] = useState("")
  const [adminLoginAllowed, setAdminLoginAllowed] = useState(false)
  const [allowLogin, setAllowLogin] = useState(true)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState("")
  const [newTitle, setNewTitle] = useState("")
  const [collapsedPermGroups, setCollapsedPermGroups] = useState<Set<string>>(new Set())
  const [deleteTarget, setDeleteTarget] = useState<Role | null>(null)

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
        admin_login_allowed: adminLoginAllowed,
        allow_login: allowLogin,
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-roles"] })
      toastSuccess("Права роли обновлены")
      setEditing(null)
    },
    onError: () => toastError("Не удалось сохранить права роли"),
  })

  const create = useMutation({
    mutationFn: async () => {
      await api.post("/v1/admin/roles", {
        name: newName.trim(),
        title: newTitle.trim() || null,
        perms: buildPermsTree(Array.from(checked)),
        admin_login_allowed: adminLoginAllowed,
        allow_login: allowLogin,
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-roles"] })
      toastSuccess("Роль создана")
      setCreating(false)
      setNewName("")
      setNewTitle("")
    },
    onError: () => toastError("Не удалось создать роль"),
  })

  const remove = useMutation({
    mutationFn: async (role: Role) => {
      await api.delete(`/v1/admin/roles/${role.id}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-roles"] })
      toastSuccess("Роль удалена")
    },
    onError: () => toastError("Роль нельзя удалить: сначала снимите назначения"),
  })

  function openEdit(role: Role) {
    const flat = catalog?.flat ?? []
    setChecked(new Set(flat.filter((p) => hasPerm(role.perms, p))))
    setPermFilter("")
    setAdminLoginAllowed(role.admin_login_allowed)
    setAllowLogin(role.allow_login)
    setEditing(role)
  }

  const permissionTree = (catalog?.tree ?? {}) as PermTree
  const filteredPerms = useMemo(() => {
    const flat = catalog?.flat ?? []
    if (!permFilter.trim()) return flat
    const q = permFilter.trim().toLowerCase()
    return flat.filter((p) => p.toLowerCase().includes(q))
  }, [catalog, permFilter])

  function togglePermission(path: string, enabled: boolean) {
    const descendants = (catalog?.flat ?? []).filter(
      (permission) => permission === path || permission.startsWith(`${path}.`),
    )
    setChecked((prev) => {
      const next = new Set(prev)
      descendants.forEach((permission) =>
        enabled ? next.add(permission) : next.delete(permission),
      )
      return next
    })
  }

  function togglePermissionGroup(path: string) {
    setCollapsedPermGroups((previous) => {
      const next = new Set(previous)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  function permissionRows(tree: PermTree, prefix = "", depth = 0): JSX.Element[] {
    return Object.entries(tree).flatMap(([key, value]) => {
      const path = prefix ? `${prefix}.${key}` : key
      const descendants = treePaths({ [key]: value }, prefix)
      const selected = descendants.filter((item) => checked.has(item))
      const isLeaf = value === true || Object.keys(value).length === 0
      const isExpanded = depth === 0 ? !collapsedPermGroups.has(path) : collapsedPermGroups.has(path)
      const isCollapsed = !isExpanded
      const isPartiallySelected = selected.length > 0 && selected.length < descendants.length
      const row = (
        <div key={path} className={`flex min-h-8 items-center gap-1 rounded-md text-sm hover:bg-muted/50 ${!isLeaf ? "bg-muted/20" : ""}`}>
          {!isLeaf ? (
            <button
              type="button"
              className="flex size-6 shrink-0 items-center justify-center rounded hover:bg-muted"
              aria-label={isCollapsed ? `Развернуть ${key}` : `Свернуть ${key}`}
              onClick={() => togglePermissionGroup(path)}
            >
              <ChevronRight className={`size-4 transition-transform ${isCollapsed ? "" : "rotate-90"}`} />
            </button>
          ) : (
            <span className="size-6 shrink-0" />
          )}
          <Checkbox
            checked={selected.length === descendants.length && descendants.length > 0}
            onCheckedChange={(v) => togglePermission(path, !!v)}
            aria-label={`Выбрать ${path}`}
          />
          <span className={isLeaf ? "font-mono text-xs" : "font-semibold"}>{key}</span>
          {!isLeaf && isPartiallySelected && (
            <Minus className="ml-1 size-3.5 text-primary" aria-label="Выбрано частично" />
          )}
        </div>
      )
      if (isLeaf || isCollapsed) return [row]
      return [
        row,
        <div
          key={`${path}-children`}
          className="ml-3 border-l border-border/70 pl-2"
        >
          {permissionRows(value, path, depth + 1)}
        </div>,
      ]
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Роли</h1>
        <div className="flex items-center gap-2">
          {roles && <span className="text-sm text-muted-foreground">Всего: {roles.length}</span>}
          <Button onClick={() => {
            setChecked(new Set())
            setAdminLoginAllowed(false)
            setAllowLogin(true)
            setCreating(true)
          }}>
            Создать роль
          </Button>
        </div>
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Название</TableHead>
              <TableHead>Тип</TableHead>
              <TableHead>Вход в админку</TableHead>
              <TableHead>Логин</TableHead>
              <TableHead>Прав</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                  Загрузка…
                </TableCell>
              </TableRow>
            )}
            {roles?.map((r) => (
              <TableRow
                key={r.id}
                className={r.name !== "owner" ? "cursor-pointer" : undefined}
                onClick={() => r.name !== "owner" && openEdit(r)}
              >
                <TableCell>{r.id}</TableCell>
                <TableCell>
                  <span className="font-medium">{r.title ?? r.name}</span>
                  <span className="ml-1.5 text-xs text-muted-foreground">{r.name}</span>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {r.name === "owner" ? (
                      <Badge variant="outline">owner — неприкасаема</Badge>
                    ) : r.is_system ? (
                      <Badge variant="secondary">системная</Badge>
                    ) : (
                      <Badge variant="outline">кастомная</Badge>
                    )}
                    {(r.name === "media" || r.name === "support") && (
                      <Badge variant="outline" className="text-muted-foreground">
                        зарезервирована — пока не используется
                      </Badge>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  {r.name === "owner" ? (
                    <Badge variant="secondary">всегда</Badge>
                  ) : r.admin_login_allowed ? (
                    <Badge variant="secondary">разрешён</Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground">
                      запрещён
                    </Badge>
                  )}
                </TableCell>
                <TableCell>
                  {r.name === "owner" ? (
                    <Badge variant="secondary">всегда</Badge>
                  ) : r.allow_login ? (
                    <Badge variant="secondary">разрешён</Badge>
                  ) : (
                    <Badge variant="destructive">запрещён</Badge>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {catalog ? catalog.flat.filter((p) => hasPerm(r.perms, p)).length : "—"}
                </TableCell>
                <TableCell>
                  {!r.is_system && !r.is_protected && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(event) => {
                        event.stopPropagation()
                        setDeleteTarget(r)
                      }}
                    >
                      <Trash2 className="size-4" />
                      <span className="sr-only">Удалить роль</span>
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
          <label className="flex items-center gap-2 rounded border px-2.5 py-2 text-sm">
            <Checkbox
              checked={adminLoginAllowed}
              onCheckedChange={(v) => setAdminLoginAllowed(!!v)}
            />
            <span>
              Разрешить вход в админ-панель
              <span className="ml-1 block text-xs text-muted-foreground">
                Без этого флага роль не может войти в админку, даже если у неё есть права.
              </span>
            </span>
          </label>
          <label className="flex items-center gap-2 rounded border px-2.5 py-2 text-sm">
            <Checkbox
              checked={allowLogin}
              onCheckedChange={(v) => setAllowLogin(!!v)}
            />
            <span>
              Разрешить получение/обновление токенов (логин)
              <span className="ml-1 block text-xs text-muted-foreground">
                Без этого флага аккаунты с этой ролью не могут залогиниться и
                обновить токен вообще — жёсткая блокировка независимо от прав.
              </span>
            </span>
          </label>
          <div className="max-h-[45vh] space-y-1 overflow-y-auto pr-1">
            {permFilter.trim()
              ? filteredPerms.map((p) => (
                <label key={p} className="flex items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-muted/50">
                  <Checkbox checked={checked.has(p)} onCheckedChange={(v) => togglePermission(p, !!v)} />
                  <span className="font-mono text-xs">{p}</span>
                </label>
              ))
              : permissionRows(permissionTree)}
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

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-h-[80vh] max-w-lg overflow-hidden">
          <DialogHeader>
            <DialogTitle>Новая роль</DialogTitle>
            <DialogDescription>Создайте пользовательскую роль и задайте её права.</DialogDescription>
          </DialogHeader>
          <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Системное имя" />
          <Input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="Отображаемое название (необязательно)" />
          <div className="max-h-[40vh] space-y-1 overflow-y-auto pr-1">{permissionRows(permissionTree)}</div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={adminLoginAllowed} onCheckedChange={(v) => setAdminLoginAllowed(!!v)} />
            Разрешить вход в админ-панель
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={allowLogin} onCheckedChange={(v) => setAllowLogin(!!v)} />
            Разрешить логин и обновление токенов
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreating(false)}>Отмена</Button>
            <Button onClick={() => create.mutate()} disabled={!newName.trim() || create.isPending}>Создать</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить роль «{deleteTarget?.title ?? deleteTarget?.name}»?</AlertDialogTitle>
            <AlertDialogDescription>
              Удаление необратимо. Системные роли удалить нельзя, а для занятой роли backend отклонит операцию.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => {
                if (deleteTarget) remove.mutate(deleteTarget)
                setDeleteTarget(null)
              }}
            >
              Удалить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
