import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MoreHorizontal, Plus, Trash2, Zap } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
import { Textarea } from "@/components/shadsnui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import { Card, CardContent } from "@/components/shadsnui/card"
import {
  Dialog,
  DialogContent,
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/shadsnui/dropdown-menu"
import { toastError, toastSuccess } from "@/lib/toast"

interface Trigger {
  id: number
  name: string | null
  event: string
  action: string
  config: Record<string, unknown>
  cond: Record<string, unknown>
  is_active: boolean
}

interface TriggerMeta {
  events: string[]
  actions: string[]
}

interface EmailTemplate {
  id: number
  slug: string
  name: string | null
}

interface LuaScript {
  id: number
  name: string
}

const EVENT_LABEL: Record<string, string> = {
  "user.registered": "Регистрация пользователя",
  "user.verified": "Подтверждение email",
  "order.created": "Заказ создан",
  "payment.paid": "Платёж оплачен",
  "payment.refunded": "Платёж возвращён",
  "service.delivered": "Услуга выдана",
}

function errDetail(e: unknown): string | undefined {
  if (e && typeof e === "object" && "response" in e) {
    // @ts-expect-error — axios error shape
    const d = e.response?.data?.detail
    return typeof d === "string" ? d : undefined
  }
  return undefined
}

function TriggerFormDialog({
  open,
  onOpenChange,
  trigger,
  meta,
  templates,
  scripts,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  trigger: Trigger | null
  meta: TriggerMeta | undefined
  templates: EmailTemplate[] | undefined
  scripts: LuaScript[] | undefined
}) {
  const isEdit = !!trigger
  const [name, setName] = useState(trigger?.name ?? "")
  const [event, setEvent] = useState(trigger?.event ?? meta?.events[0] ?? "")
  const [action, setAction] = useState(trigger?.action ?? "email")
  const [templateId, setTemplateId] = useState(
    trigger?.action === "email" ? String((trigger.config as { template_id?: number }).template_id ?? "") : "",
  )
  const [toField, setToField] = useState(
    trigger?.action === "email" ? String((trigger.config as { to_field?: string }).to_field ?? "") : "",
  )
  const [scriptId, setScriptId] = useState(
    trigger?.action === "lua" ? String((trigger.config as { script_id?: number }).script_id ?? "") : "",
  )
  const [condText, setCondText] = useState(JSON.stringify(trigger?.cond ?? {}, null, 2))
  const [isActive, setIsActive] = useState(trigger?.is_active ?? true)
  const [jsonError, setJsonError] = useState<string | null>(null)
  const qc = useQueryClient()

  const save = useMutation({
    mutationFn: async () => {
      let cond: unknown
      try {
        cond = JSON.parse(condText)
      } catch {
        setJsonError("Условия должны быть корректным JSON")
        throw new Error("invalid json")
      }
      setJsonError(null)
      const config =
        action === "email"
          ? { template_id: Number(templateId), ...(toField ? { to_field: toField } : {}) }
          : { script_id: Number(scriptId) }
      const body = { name: name || null, event, action, config, cond, is_active: isActive }
      if (isEdit) return api.patch(`/v1/admin/triggers/${trigger!.id}`, body)
      return api.post("/v1/admin/triggers", body)
    },
    onSuccess: () => {
      toastSuccess(isEdit ? "Триггер обновлён" : "Триггер создан")
      onOpenChange(false)
      void qc.invalidateQueries({ queryKey: ["admin-triggers"] })
    },
    onError: (e: unknown) => {
      if ((e as Error).message !== "invalid json") {
        toastError(isEdit ? "Не удалось обновить триггер" : "Не удалось создать триггер", errDetail(e))
      }
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Изменить триггер" : "Новый триггер"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Название (опционально)</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <div className="space-y-1">
            <Label>Событие</Label>
            <Select value={event} onValueChange={(v) => setEvent(v ?? "")}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {meta?.events.map((ev) => (
                  <SelectItem key={ev} value={ev}>
                    {EVENT_LABEL[ev] ?? ev}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Действие</Label>
            <Select value={action} onValueChange={(v) => setAction(v ?? "email")}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {meta?.actions.map((a) => (
                  <SelectItem key={a} value={a}>
                    {a === "email" ? "Отправить письмо" : "Выполнить Lua-скрипт"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {action === "email" ? (
            <>
              <div className="space-y-1">
                <Label>Шаблон письма</Label>
                <Select value={templateId} onValueChange={(v) => setTemplateId(v ?? "")}>
                  <SelectTrigger>
                    <SelectValue placeholder="Выберите шаблон" />
                  </SelectTrigger>
                  <SelectContent>
                    {templates?.map((t) => (
                      <SelectItem key={t.id} value={String(t.id)}>
                        {t.name ?? t.slug}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Путь к email получателя в контексте</Label>
                <Input value={toField} onChange={(e) => setToField(e.target.value)} placeholder="user.email" />
              </div>
            </>
          ) : (
            <div className="space-y-1">
              <Label>Lua-скрипт</Label>
              <Select value={scriptId} onValueChange={(v) => setScriptId(v ?? "")}>
                <SelectTrigger>
                  <SelectValue placeholder="Выберите скрипт" />
                </SelectTrigger>
                <SelectContent>
                  {scripts?.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-1">
            <Label>Дополнительные условия (JSON, все должны совпасть)</Label>
            <Textarea
              className="font-mono text-xs"
              rows={3}
              value={condText}
              onChange={(e) => setCondText(e.target.value)}
              placeholder='{"payment.target": "service"}'
            />
            {jsonError && <p className="text-xs text-destructive">{jsonError}</p>}
          </div>
          <div className="flex items-center justify-between">
            <Label>Активен</Label>
            <Switch checked={isActive} onCheckedChange={setIsActive} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            disabled={
              !event ||
              (action === "email" ? !templateId : !scriptId) ||
              save.isPending
            }
            onClick={() => save.mutate()}
          >
            {isEdit ? "Сохранить" : "Создать"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DeleteTriggerDialog({
  trigger,
  open,
  onOpenChange,
}: {
  trigger: Trigger
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const del = useMutation({
    mutationFn: async () => api.delete(`/v1/admin/triggers/${trigger.id}`),
    onSuccess: () => {
      toastSuccess("Триггер удалён")
      onOpenChange(false)
      void qc.invalidateQueries({ queryKey: ["admin-triggers"] })
    },
    onError: (e: unknown) => toastError("Не удалось удалить триггер", errDetail(e)),
  })

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Удалить триггер «{trigger.name ?? EVENT_LABEL[trigger.event] ?? trigger.event}»?</AlertDialogTitle>
          <AlertDialogDescription>Действие необратимо.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Отмена</AlertDialogCancel>
          <AlertDialogAction
            disabled={del.isPending}
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

export function TriggersPage() {
  const { can } = useAuth()
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Trigger | null>(null)
  const [deleting, setDeleting] = useState<Trigger | null>(null)

  const canCreate = can("triggers.create")
  const canEdit = can("triggers.edit")
  const canDelete = can("triggers.delete")

  const { data: meta } = useQuery({
    queryKey: ["admin-triggers-meta"],
    queryFn: async () => (await api.get<TriggerMeta>("/v1/admin/triggers/meta")).data,
  })

  const { data: templates } = useQuery({
    queryKey: ["admin-email-templates-lookup"],
    queryFn: async () => (await api.get<EmailTemplate[]>("/v1/admin/email/templates")).data,
    staleTime: 60_000,
  })

  const { data: scripts } = useQuery({
    queryKey: ["admin-lua-scripts-lookup"],
    queryFn: async () => (await api.get<LuaScript[]>("/v1/admin/lua")).data,
    staleTime: 60_000,
  })

  const { data, isLoading } = useQuery({
    queryKey: ["admin-triggers"],
    queryFn: async () => (await api.get<Trigger[]>("/v1/admin/triggers")).data,
  })

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Триггеры</h1>
        {canCreate && (
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="size-4" /> Создать
          </Button>
        )}
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
      {!isLoading && (data?.length ?? 0) === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
            <Zap className="size-6" />
            Триггеров пока нет — создайте первый, чтобы автоматизировать письма/скрипты по событиям.
          </CardContent>
        </Card>
      )}

      <div className="grid gap-2">
        {data?.map((t) => (
          <Card key={t.id}>
            <CardContent className="flex items-center justify-between gap-3 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium">{t.name ?? EVENT_LABEL[t.event] ?? t.event}</span>
                  <Badge variant="outline">{EVENT_LABEL[t.event] ?? t.event}</Badge>
                  <Badge variant="secondary">{t.action === "email" ? "письмо" : "lua"}</Badge>
                  {!t.is_active && <Badge variant="destructive">выключен</Badge>}
                </div>
                {Object.keys(t.cond).length > 0 && (
                  <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
                    условия: {JSON.stringify(t.cond)}
                  </p>
                )}
              </div>
              {(canEdit || canDelete) && (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button variant="ghost" size="icon" className="size-8 shrink-0">
                        <MoreHorizontal className="size-4" />
                      </Button>
                    }
                  />
                  <DropdownMenuContent align="end">
                    {canEdit && <DropdownMenuItem onClick={() => setEditing(t)}>Изменить</DropdownMenuItem>}
                    {canDelete && (
                      <DropdownMenuItem variant="destructive" onClick={() => setDeleting(t)}>
                        <Trash2 className="size-4" /> Удалить
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <TriggerFormDialog
        open={creating}
        onOpenChange={setCreating}
        trigger={null}
        meta={meta}
        templates={templates}
        scripts={scripts}
      />
      {editing && (
        <TriggerFormDialog
          open={!!editing}
          onOpenChange={(v) => !v && setEditing(null)}
          trigger={editing}
          meta={meta}
          templates={templates}
          scripts={scripts}
        />
      )}
      {deleting && (
        <DeleteTriggerDialog trigger={deleting} open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)} />
      )}
    </div>
  )
}
