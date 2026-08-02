import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Mail, MoreHorizontal, Plus, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Switch } from "@/components/shadsnui/switch"
import { Textarea } from "@/components/shadsnui/textarea"
import { Card, CardContent } from "@/components/shadsnui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/shadsnui/tabs"
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

interface Template {
  id: number
  slug: string
  name: string | null
  subject: string
  is_html: boolean
  is_active: boolean
}

interface TemplateDetail extends Template {
  body: string
  description?: string | null
}

function errDetail(e: unknown): string | undefined {
  if (e && typeof e === "object" && "response" in e) {
    // @ts-expect-error — axios error shape
    const d = e.response?.data?.detail
    return typeof d === "string" ? d : undefined
  }
  return undefined
}

function CreateTemplateDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [slug, setSlug] = useState("")
  const [name, setName] = useState("")
  const [subject, setSubject] = useState("")
  const [body, setBody] = useState("")
  const [isHtml, setIsHtml] = useState(true)
  const qc = useQueryClient()

  const reset = () => {
    setSlug("")
    setName("")
    setSubject("")
    setBody("")
    setIsHtml(true)
  }

  const create = useMutation({
    mutationFn: async () => api.post("/v1/admin/email/templates", { slug, name: name || null, subject, body, is_html: isHtml }),
    onSuccess: () => {
      toastSuccess("Шаблон создан")
      onOpenChange(false)
      reset()
      void qc.invalidateQueries({ queryKey: ["admin-email-templates"] })
    },
    onError: (e: unknown) => toastError("Не удалось создать шаблон", errDetail(e)),
  })

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset() }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Новый email-шаблон</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Слаг (используется в коде для отправки)</Label>
            <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="order.delivered" autoFocus />
          </div>
          <div className="space-y-1">
            <Label>Название</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Услуга выдана" />
          </div>
          <div className="space-y-1">
            <Label>Тема письма (Jinja2)</Label>
            <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Ваш заказ {{ order.id }} готов" />
          </div>
          <div className="space-y-1">
            <Label>Тело письма (Jinja2, {isHtml ? "HTML" : "текст"})</Label>
            <Textarea
              className="font-mono text-xs"
              rows={8}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Здравствуйте, {{ user.login }}!"
            />
          </div>
          <div className="flex items-center justify-between">
            <Label>HTML-письмо</Label>
            <Switch checked={isHtml} onCheckedChange={setIsHtml} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button
            disabled={slug.trim().length < 2 || subject.trim().length < 1 || body.trim().length < 1 || create.isPending}
            onClick={() => create.mutate()}
          >
            Создать
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function EditTemplateDialog({
  template,
  onOpenChange,
}: {
  template: Template
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()

  const { data: detail, isLoading } = useQuery({
    queryKey: ["admin-email-template-detail", template.id],
    queryFn: async () => (await api.get<TemplateDetail>(`/v1/admin/email/templates/${template.id}`)).data,
  })

  const [name, setName] = useState<string | null>(null)
  const [subject, setSubject] = useState<string | null>(null)
  const [isActive, setIsActive] = useState<boolean | null>(null)
  const [body, setBody] = useState<string | null>(null)

  const effName = name ?? detail?.name ?? ""
  const effSubject = subject ?? detail?.subject ?? ""
  const effIsActive = isActive ?? detail?.is_active ?? true
  const effBody = body ?? detail?.body ?? ""

  const saveMeta = useMutation({
    mutationFn: async () =>
      api.patch(`/v1/admin/email/templates/${template.id}`, {
        name: effName || null,
        subject: effSubject,
        is_active: effIsActive,
      }),
    onSuccess: () => {
      toastSuccess("Шаблон сохранён")
      void qc.invalidateQueries({ queryKey: ["admin-email-templates"] })
      void qc.invalidateQueries({ queryKey: ["admin-email-template-detail", template.id] })
    },
    onError: (e: unknown) => toastError("Не удалось сохранить шаблон", errDetail(e)),
  })

  const saveBody = useMutation({
    mutationFn: async () => api.put(`/v1/admin/email/templates/${template.id}/body`, { body: effBody }),
    onSuccess: () => {
      toastSuccess("Тело письма сохранено")
      void qc.invalidateQueries({ queryKey: ["admin-email-template-detail", template.id] })
    },
    onError: (e: unknown) => toastError("Не удалось сохранить тело письма", errDetail(e)),
  })

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{template.name ?? template.slug}</DialogTitle>
        </DialogHeader>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Загрузка…</p>
        ) : (
          <Tabs defaultValue="meta">
            <TabsList>
              <TabsTrigger value="meta">Основное</TabsTrigger>
              <TabsTrigger value="body">Тело письма</TabsTrigger>
            </TabsList>
            <TabsContent value="meta" className="space-y-3">
              <div className="space-y-1">
                <Label>Название</Label>
                <Input value={effName} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>Тема письма (Jinja2)</Label>
                <Input value={effSubject} onChange={(e) => setSubject(e.target.value)} />
              </div>
              <div className="flex items-center justify-between">
                <Label>Активен</Label>
                <Switch checked={effIsActive} onCheckedChange={setIsActive} />
              </div>
              <Button size="sm" disabled={saveMeta.isPending} onClick={() => saveMeta.mutate()}>
                Сохранить
              </Button>
            </TabsContent>
            <TabsContent value="body" className="space-y-3">
              <Textarea
                className="font-mono text-xs"
                rows={14}
                value={effBody}
                onChange={(e) => setBody(e.target.value)}
              />
              <Button size="sm" disabled={saveBody.isPending} onClick={() => saveBody.mutate()}>
                Сохранить тело письма
              </Button>
            </TabsContent>
          </Tabs>
        )}
      </DialogContent>
    </Dialog>
  )
}

function DeleteTemplateDialog({
  template,
  open,
  onOpenChange,
}: {
  template: Template
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const del = useMutation({
    mutationFn: async () => api.delete(`/v1/admin/email/templates/${template.id}`),
    onSuccess: () => {
      toastSuccess("Шаблон удалён")
      onOpenChange(false)
      void qc.invalidateQueries({ queryKey: ["admin-email-templates"] })
    },
    onError: (e: unknown) => toastError("Не удалось удалить шаблон", errDetail(e)),
  })

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Удалить шаблон «{template.name ?? template.slug}»?</AlertDialogTitle>
          <AlertDialogDescription>
            Триггеры, использующие этот шаблон, перестанут отправлять письма.
          </AlertDialogDescription>
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

export function EmailTemplatesPage() {
  const { can } = useAuth()
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Template | null>(null)
  const [deleting, setDeleting] = useState<Template | null>(null)

  const canCreate = can("email.create")
  const canEdit = can("email.edit")
  const canDelete = can("email.delete")

  const { data, isLoading } = useQuery({
    queryKey: ["admin-email-templates"],
    queryFn: async () => (await api.get<Template[]>("/v1/admin/email/templates")).data,
  })

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Email-шаблоны</h1>
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
            <Mail className="size-6" />
            Шаблонов пока нет.
          </CardContent>
        </Card>
      )}

      <div className="grid gap-2">
        {data?.map((t) => (
          <Card key={t.id} className="cursor-pointer" onClick={() => canEdit && setEditing(t)}>
            <CardContent className="flex items-center justify-between gap-3 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium">{t.name ?? t.slug}</span>
                  <span className="font-mono text-xs text-muted-foreground">{t.slug}</span>
                  {!t.is_active && <Badge variant="destructive">выключен</Badge>}
                  <Badge variant="outline">{t.is_html ? "HTML" : "текст"}</Badge>
                </div>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">{t.subject}</p>
              </div>
              {canDelete && (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8 shrink-0"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <MoreHorizontal className="size-4" />
                      </Button>
                    }
                  />
                  <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
                    <DropdownMenuItem variant="destructive" onClick={() => setDeleting(t)}>
                      <Trash2 className="size-4" /> Удалить
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <CreateTemplateDialog open={creating} onOpenChange={setCreating} />
      {editing && <EditTemplateDialog template={editing} onOpenChange={(v) => !v && setEditing(null)} />}
      {deleting && (
        <DeleteTemplateDialog template={deleting} open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)} />
      )}
    </div>
  )
}
