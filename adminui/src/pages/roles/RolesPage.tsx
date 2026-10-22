import { useMemo, useState, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronRight, KeyRound, Minus, ShieldCheck, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { hasPerm, type PermNode } from "@/api/rbac.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import { Badge } from "@/components/shadsnui/badge"
import { Checkbox } from "@/components/shadsnui/checkbox"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
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
import { TabbedDialog, type TabDefinition } from "@/components/common/TabbedDialog"

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

interface RoleImpact {
  assigned_accounts: number
  is_system: boolean
  is_protected: boolean
  can_delete: boolean
}

interface PermTree {
  [key: string]: PermTree | boolean
}

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
    if (value === true) return [path]
    if (typeof value === "object" && value !== null) {
      const keys = Object.keys(value)
      return keys.length === 0 ? [path] : treePaths(value as PermTree, path)
    }
    return [path]
  })
}

export function RolesPage() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<Role | null>(null)
  const [editTitle, setEditTitle] = useState("")
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

  const { data: deleteImpact, isLoading: isImpactLoading, isError: isImpactError } = useQuery({
    queryKey: ["admin-role-impact", deleteTarget?.id],
    queryFn: async () => (
      await api.get<RoleImpact>(`/v1/admin/roles/${deleteTarget!.id}/impact`)
    ).data,
    enabled: deleteTarget !== null,
  })

  const save = useMutation({
    mutationFn: async () => {
      if (!editing) return
      await api.patch(`/v1/admin/roles/${editing.id}`, {
        title: editTitle.trim() || null,
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
    setEditTitle(role.title ?? "")
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

  function permissionRows(tree: PermTree, prefix = "", depth = 0): ReactNode[] {
    return Object.entries(tree).flatMap(([key, value]) => {
      const path = prefix ? `${prefix}.${key}` : key
      const descendants = treePaths({ [key]: value }, prefix)
      const selected = descendants.filter((item) => checked.has(item))
      const isLeaf = value === true || (typeof value === "object" && value !== null && Object.keys(value).length === 0)
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
          {permissionRows(value as PermTree, path, depth + 1)}
        </div>,
      ]
    })
  }

  const editTabs: TabDefinition[] = editing ? [
    {
      id: "general",
      label: "Свойства роли",
      icon: ShieldCheck,
      content: (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Системный идентификатор роли</Label>
            <div className="flex items-center gap-2">
              <Input value={editing.name} disabled className="font-mono text-xs bg-muted/40" />
              {editing.is_system && <Badge variant="secondary">системная</Badge>}
              {editing.is_protected && <Badge variant="outline">защищенная</Badge>}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Отображаемое название роли</Label>
            <Input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              placeholder="Менеджер контента"
              className="text-xs"
            />
          </div>

          <div className="space-y-3 rounded-lg border border-border/60 bg-muted/20 p-3">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label className="text-xs font-medium">Вход в панель администратора</Label>
                <p className="text-[10px] text-muted-foreground">
                  Без этого флага роль не может зайти в админку, даже имея права
                </p>
              </div>
              <Switch checked={adminLoginAllowed} onCheckedChange={setAdminLoginAllowed} />
            </div>

            <div className="border-t border-border/40 pt-2 flex items-center justify-between">
              <div className="space-y-0.5">
                <Label className="text-xs font-medium">Получение и обновление токенов (Логин)</Label>
                <p className="text-[10px] text-muted-foreground">
                  Блокирует авторизацию всех пользователей с этой ролью
                </p>
              </div>
              <Switch checked={allowLogin} onCheckedChange={setAllowLogin} />
            </div>
          </div>
        </div>
      ),
    },
    {
      id: "permissions",
      label: "Права доступа",
      icon: KeyRound,
      badge: `${checked.size}`,
      content: (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Input
              value={permFilter}
              onChange={(e) => setPermFilter(e.target.value)}
              placeholder="Быстрый поиск права (например: services.edit)..."
              className="h-8 text-xs"
            />
            {permFilter && (
              <Button size="sm" variant="ghost" onClick={() => setPermFilter("")} className="h-8 text-xs">
                Сбросить
              </Button>
            )}
          </div>

          <div className="max-h-[350px] overflow-y-auto rounded-lg border border-border/60 p-2.5 space-y-1 bg-background/50">
            {permFilter.trim() ? (
              filteredPerms.map((p) => (
                <label key={p} className="flex items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-muted/50 cursor-pointer">
                  <Checkbox checked={checked.has(p)} onCheckedChange={(v) => togglePermission(p, !!v)} />
                  <span className="font-mono text-xs">{p}</span>
                </label>
              ))
            ) : (
              permissionRows(permissionTree)
            )}
          </div>
        </div>
      ),
    },
  ] : []

  const createTabs: TabDefinition[] = [
    {
      id: "general",
      label: "Свойства роли",
      icon: ShieldCheck,
      content: (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Системное имя роли (slug)</Label>
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="support_lead"
              className="font-mono text-xs"
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Отображаемое название (необязательно)</Label>
            <Input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Старший специалист поддержки"
              className="text-xs"
            />
          </div>

          <div className="space-y-3 rounded-lg border border-border/60 bg-muted/20 p-3">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label className="text-xs font-medium">Вход в панель администратора</Label>
                <p className="text-[10px] text-muted-foreground">
                  Разрешить вход в интерфейс панели управления
                </p>
              </div>
              <Switch checked={adminLoginAllowed} onCheckedChange={setAdminLoginAllowed} />
            </div>

            <div className="border-t border-border/40 pt-2 flex items-center justify-between">
              <div className="space-y-0.5">
                <Label className="text-xs font-medium">Разрешить логин</Label>
                <p className="text-[10px] text-muted-foreground">
                  Разрешить пользователям с этой ролью входить в систему
                </p>
              </div>
              <Switch checked={allowLogin} onCheckedChange={setAllowLogin} />
            </div>
          </div>
        </div>
      ),
    },
    {
      id: "permissions",
      label: "Права доступа",
      icon: KeyRound,
      badge: `${checked.size}`,
      content: (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Input
              value={permFilter}
              onChange={(e) => setPermFilter(e.target.value)}
              placeholder="Фильтр прав..."
              className="h-8 text-xs"
            />
          </div>

          <div className="max-h-[350px] overflow-y-auto rounded-lg border border-border/60 p-2.5 space-y-1 bg-background/50">
            {permFilter.trim() ? (
              filteredPerms.map((p) => (
                <label key={p} className="flex items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-muted/50 cursor-pointer">
                  <Checkbox checked={checked.has(p)} onCheckedChange={(v) => togglePermission(p, !!v)} />
                  <span className="font-mono text-xs">{p}</span>
                </label>
              ))
            ) : (
              permissionRows(permissionTree)
            )}
          </div>
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold">Роли и права доступа</h1>
          <p className="text-sm text-muted-foreground">
            Управление правами доступа (RBAC), системными ролями и разрешениями
          </p>
        </div>
        <div className="flex items-center gap-2">
          {roles && <span className="text-sm text-muted-foreground">Всего: {roles.length}</span>}
          <Button onClick={() => {
            setChecked(new Set())
            setAdminLoginAllowed(false)
            setAllowLogin(true)
            setNewName("")
            setNewTitle("")
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

      {editing && (
        <TabbedDialog
          open={!!editing}
          onOpenChange={(v) => !v && setEditing(null)}
          title={`Роль «${editing.title ?? editing.name}»`}
          description="Редактирование параметров и матрицы разрешений роли"
          tabs={editTabs}
          primaryAction={{
            label: "Сохранить изменения",
            onClick: () => save.mutate(),
            loading: save.isPending,
          }}
          secondaryAction={{
            label: "Отмена",
            onClick: () => setEditing(null),
          }}
        />
      )}

      {creating && (
        <TabbedDialog
          open={creating}
          onOpenChange={setCreating}
          title="Новая роль"
          description="Создание пользовательской роли и настройка прав доступа"
          tabs={createTabs}
          primaryAction={{
            label: "Создать роль",
            onClick: () => create.mutate(),
            disabled: !newName.trim() || create.isPending,
            loading: create.isPending,
          }}
          secondaryAction={{
            label: "Отмена",
            onClick: () => setCreating(false),
          }}
        />
      )}

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить роль «{deleteTarget?.title ?? deleteTarget?.name}»?</AlertDialogTitle>
            <AlertDialogDescription>
              {isImpactLoading
                ? "Проверяем назначения роли…"
                : isImpactError
                  ? "Не удалось проверить назначения роли. Удаление может быть заблокировано сервером."
                  : deleteImpact && deleteImpact.assigned_accounts > 0
                    ? `Роль назначена ${deleteImpact.assigned_accounts} аккаунтам. Удаление будет отклонено — сначала снимите её со всех пользователей.`
                    : "Роль не назначена ни одному аккаунту и будет удалена безвозвратно."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              disabled={remove.isPending || (deleteImpact ? !deleteImpact.can_delete : false)}
              onClick={() => deleteTarget && remove.mutate(deleteTarget)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Удалить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
