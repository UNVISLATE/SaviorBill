import { useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Mail, MoreHorizontal, PlayCircle, Plus, SlidersHorizontal, Trash2, Zap } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
import { Card, CardContent } from "@/components/shadsnui/card"
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/shadsnui/dropdown-menu"
import { TabbedDialog, type TabDefinition } from "@/components/common/TabbedDialog"
import { ConditionRuleBuilder } from "@/components/common/forms/ConditionRuleBuilder"
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
  "service.keys.low": "Мало ключей в остатке",
  "service.keys.empty": "Ключи закончились",
  "payment.cancelled": "Платёж отменён",
  "payment.failed": "Ошибка платежа",
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
  const [name, setName] = useState("")
  const [event, setEvent] = useState("")
  const [action, setAction] = useState("email")
  const [templateId, setTemplateId] = useState("")
  const [toField, setToField] = useState("")
  const [scriptId, setScriptId] = useState("")
  const [condText, setCondText] = useState("{}")
  const [isActive, setIsActive] = useState(true)
  const qc = useQueryClient()

  useEffect(() => {
    if (open) {
      setName(trigger?.name ?? "")
      setEvent(trigger?.event ?? meta?.events[0] ?? "payment.paid")
      setAction(trigger?.action ?? "email")
      setTemplateId(
        trigger?.action === "email" ? String((trigger.config as { template_id?: number }).template_id ?? "") : "",
      )
      setToField(
        trigger?.action === "email" ? String((trigger.config as { to_field?: string }).to_field ?? "") : "",
      )
      setScriptId(
        trigger?.action === "lua" ? String((trigger.config as { script_id?: number }).script_id ?? "") : "",
      )
      setCondText(JSON.stringify(trigger?.cond ?? {}, null, 2))
      setIsActive(trigger?.is_active ?? true)
    }
  }, [open, trigger, meta])

  const save = useMutation({
    mutationFn: async () => {
      let cond: unknown
      try {
        cond = JSON.parse(condText)
      } catch {
        throw new Error("invalid json")
      }
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
      toastError(
        isEdit ? "Не удалось обновить триггер" : "Не удалось создать триггер",
        (e as Error).message === "invalid json" ? "Условия должны быть корректным JSON" : getErrorDetail(e),
      )
    },
  })

  const tabs: TabDefinition[] = [
    {
      id: "event",
      label: "Событие",
      icon: Zap,
      content: (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Название триггера (опционально)</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Например: Уведомление об успешной оплате"
              className="text-xs"
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Доменное событие системы</Label>
            <Select value={event} onValueChange={(v) => v && setEvent(v)}>
              <SelectTrigger className="text-xs">
                <SelectValue placeholder="Выберите событие" />
              </SelectTrigger>
              <SelectContent>
                {meta?.events.map((ev) => (
                  <SelectItem key={ev} value={ev} className="text-xs">
                    <span className="font-medium">{EVENT_LABEL[ev] ?? ev}</span>
                    <span className="font-mono text-[10px] text-muted-foreground ml-2">({ev})</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[10px] text-muted-foreground">
              Событие, при возникновении которого запускается этот сценарий
            </p>
          </div>

          <div className="flex h-9 items-center justify-between rounded-md border border-input bg-background px-3 py-1">
            <div>
              <span className="text-xs font-medium">Статус триггера</span>
              <p className="text-[10px] text-muted-foreground">Активен и обрабатывает поступающие события</p>
            </div>
            <Switch checked={isActive} onCheckedChange={setIsActive} />
          </div>
        </div>
      ),
    },
    {
      id: "action",
      label: "Действие",
      icon: action === "email" ? Mail : PlayCircle,
      content: (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Тип действия</Label>
            <Select value={action} onValueChange={(v) => v && setAction(v)}>
              <SelectTrigger className="text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {meta?.actions.map((a) => (
                  <SelectItem key={a} value={a} className="text-xs">
                    {a === "email" ? "Отправить Email-письмо" : "Выполнить Lua-скрипт"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {action === "email" ? (
            <div className="space-y-3 rounded-lg border border-border/60 bg-muted/20 p-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Шаблон Email</Label>
                <Select value={templateId} onValueChange={(v) => setTemplateId(v ?? "")}>
                  <SelectTrigger className="text-xs bg-background">
                    <SelectValue placeholder="Выберите почтовый шаблон" />
                  </SelectTrigger>
                  <SelectContent>
                    {templates?.map((t) => (
                      <SelectItem key={t.id} value={String(t.id)} className="text-xs">
                        {t.name ?? t.slug}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">Путь к получателю в контексте (JSON dot-path)</Label>
                <Input
                  value={toField}
                  onChange={(e) => setToField(e.target.value)}
                  placeholder="user.email"
                  className="font-mono text-xs bg-background"
                />
                <p className="text-[10px] text-muted-foreground">
                  По умолчанию используется email пользователя из контекста события
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-1.5 rounded-lg border border-border/60 bg-muted/20 p-3">
              <Label className="text-xs">Lua-скрипт автоматизации</Label>
              <Select value={scriptId} onValueChange={(v) => setScriptId(v ?? "")}>
                <SelectTrigger className="text-xs bg-background">
                  <SelectValue placeholder="Выберите Lua-скрипт" />
                </SelectTrigger>
                <SelectContent>
                  {scripts?.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)} className="text-xs">
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
      ),
    },
    {
      id: "conditions",
      label: "Условия фильтрации",
      icon: SlidersHorizontal,
      content: (
        <ConditionRuleBuilder
          event={event}
          value={condText}
          onChange={(_, text) => setCondText(text)}
        />
      ),
    },
  ]

  return (
    <TabbedDialog
      open={open}
      onOpenChange={onOpenChange}
      title={isEdit ? `Триггер «${trigger?.name || EVENT_LABEL[trigger?.event || ""] || trigger?.event}»` : "Новый триггер"}
      description="Автоматический запуск сценариев и уведомлений при доменных событиях"
      tabs={tabs}
      primaryAction={{
        label: isEdit ? "Сохранить изменения" : "Создать триггер",
        onClick: () => save.mutate(),
        disabled: !event || (action === "email" ? !templateId : !scriptId) || save.isPending,
        loading: save.isPending,
      }}
      secondaryAction={{
        label: "Отмена",
        onClick: () => onOpenChange(false),
      }}
    />
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
    onError: (e: unknown) => toastError("Не удалось удалить триггер", getErrorDetail(e)),
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
        <div>
          <h1 className="text-xl font-semibold">Триггеры автоматизации</h1>
          <p className="text-sm text-muted-foreground">
            Автоматическая реакция на системные события (оплата, регистрация, доставка)
          </p>
        </div>
        {canCreate && (
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="size-4" /> Создать триггер
          </Button>
        )}
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
      {!isLoading && (data?.length ?? 0) === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
            <Zap className="size-6 text-primary" />
            Триггеров пока нет — создайте первый, чтобы автоматизировать письма и Lua-скрипты по событиям.
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
                      <DropdownMenuItem
                        onClick={() => setDeleting(t)}
                        className="text-destructive focus:text-destructive"
                      >
                        <Trash2 className="size-4 mr-1.5" /> Удалить
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
