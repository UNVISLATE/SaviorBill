import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "react-router-dom"
import { ArrowLeft, Mail, MoreVertical, Plus, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { useAuth } from "@/hooks/use-auth"
import { useIsMobile } from "@/hooks/use-mobile"
import { useBreadcrumbExtra } from "@/hooks/use-breadcrumb"
import { Badge } from "@/components/shadsnui/badge"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Skeleton } from "@/components/shadsnui/skeleton"
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
import { cn } from "@/lib/utils"
import { EmailTemplateEditor, type TemplateDetail } from "./EmailTemplateEditor"
import { CreateEmailTemplateDialog } from "@/components/email/CreateEmailTemplateDialog"

interface Template {
  id: number
  slug: string
  name: string | null
  subject: string
  is_html: boolean
  is_active: boolean
}

function DeleteTemplateDialog({
  template,
  open,
  onOpenChange,
  onDeleted,
}: {
  template: Template
  open: boolean
  onOpenChange: (v: boolean) => void
  onDeleted: () => void
}) {
  const qc = useQueryClient()
  const del = useMutation({
    mutationFn: async () => api.delete(`/v1/admin/email/templates/${template.id}`),
    onSuccess: () => {
      toastSuccess("Шаблон удалён")
      onOpenChange(false)
      void qc.invalidateQueries({ queryKey: ["admin-email-templates"] })
      onDeleted()
    },
    onError: (e: unknown) => toastError("Не удалось удалить шаблон", getErrorDetail(e)),
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
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const { templateId: templateIdParam } = useParams<{ templateId?: string }>()
  const selectedId = templateIdParam ? Number(templateIdParam) : null

  const [search, setSearch] = useState("")
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<Template | null>(null)

  const canRead = can("email.read")
  const canCreate = can("email.create")
  const canEdit = can("email.edit")
  const canDelete = can("email.delete")

  const { data: templates, isLoading: templatesLoading } = useQuery({
    queryKey: ["admin-email-templates"],
    queryFn: async () => (await api.get<Template[]>("/v1/admin/email/templates")).data,
    enabled: canRead,
  })

  const {
    data: detail,
    isLoading: detailLoading,
    error: detailError,
  } = useQuery({
    queryKey: ["admin-email-template-detail", selectedId],
    queryFn: async () =>
      (await api.get<TemplateDetail>(`/v1/admin/email/templates/${selectedId}`)).data,
    enabled: canRead && selectedId !== null,
  })

  // Динамическая хлебная крошка
  useBreadcrumbExtra(detail ? detail.name ?? detail.slug : undefined)

  const filtered =
    templates?.filter((t) => {
      if (!search.trim()) return true
      const q = search.trim().toLowerCase()
      return t.slug.toLowerCase().includes(q) || (t.name ?? "").toLowerCase().includes(q)
    }) ?? []

  if (!canRead) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Недостаточно прав для просмотра email-шаблонов.
      </div>
    )
  }

  const showList = !isMobile || selectedId === null
  const showEditor = !isMobile || selectedId !== null

  const listPane = (
    <div className="flex w-full shrink-0 flex-col gap-2 md:w-64">
      <div className="flex items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">Email-шаблоны</h1>
        {canCreate && (
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="size-4" /> Создать
          </Button>
        )}
      </div>

      <Input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Поиск по названию/slug…"
      />

      <div className="flex-1 space-y-1 overflow-y-auto rounded-md border p-1.5">
        {templatesLoading && (
          <div className="space-y-1.5 p-1">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        )}

        {!templatesLoading && filtered.length === 0 && (
          <p className="p-3 text-center text-xs text-muted-foreground">Ничего не найдено</p>
        )}

        {filtered.map((t) => (
          <div
            key={t.id}
            className={cn(
              "group flex w-full items-center gap-1 rounded-md px-1 transition-colors",
              t.id === selectedId ? "bg-primary/10" : "hover:bg-muted/60",
            )}
          >
            <button
              type="button"
              onClick={() => navigate(`/emailtemplate/${t.id}`)}
              className="flex min-w-0 flex-1 flex-col gap-0.5 px-1.5 py-1.5 text-left text-sm"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium">{t.name ?? t.slug}</span>
                {!t.is_active && (
                  <Badge variant="outline" className="shrink-0 text-[10px]">
                    выключен
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className="truncate font-mono">{t.slug}</span>
                <span>·</span>
                <span className="shrink-0">{t.is_html ? "HTML" : "Текст"}</span>
              </div>
            </button>

            {canDelete && (
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7 shrink-0 text-muted-foreground"
                      aria-label={`Действия для ${t.name ?? t.slug}`}
                      onClick={(e) => e.stopPropagation()}
                    />
                  }
                >
                  <MoreVertical className="size-3.5" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-max min-w-[160px]">
                  <DropdownMenuItem
                    className="whitespace-nowrap"
                    variant="destructive"
                    onClick={() => setDeleting(t)}
                  >
                    <Trash2 className="size-4" /> Удалить шаблон
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        ))}
      </div>
    </div>
  )

  const editorPane = (
    <div className="min-w-0 flex-1 rounded-md border p-3 flex flex-col min-h-0">
      {isMobile && selectedId !== null && (
        <Button
          size="sm"
          variant="ghost"
          className="mb-2 self-start"
          onClick={() => navigate("/emailtemplate")}
        >
          <ArrowLeft className="size-4" /> К списку шаблонов
        </Button>
      )}

      {selectedId === null && (
        <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground p-8">
          <Mail className="size-10 text-muted-foreground/40 mb-1" />
          <p className="font-medium text-foreground">Выберите шаблон слева</p>
          <p className="text-xs max-w-xs text-muted-foreground">
            Вы сможете редактировать Jinja2-код и сразу видеть результат в живом окне предпросмотра.
          </p>
        </div>
      )}

      {selectedId !== null && detailLoading && (
        <div className="h-full space-y-3 p-2">
          <Skeleton className="h-10 w-1/3" />
          <Skeleton className="h-8 w-2/3" />
          <div className="grid grid-cols-2 gap-3 h-[calc(100%-6rem)]">
            <Skeleton className="size-full" />
            <Skeleton className="size-full" />
          </div>
        </div>
      )}

      {selectedId !== null && detailError && (
        <div className="flex h-full items-center justify-center text-sm text-destructive">
          Не удалось загрузить шаблон: {getErrorDetail(detailError)}
        </div>
      )}

      {selectedId !== null && detail && (
        <EmailTemplateEditor
          key={detail.id}
          template={detail}
          canEdit={canEdit}
        />
      )}
    </div>
  )

  return (
    <div className="flex h-[calc(100vh-8rem)] min-h-0 flex-col gap-4">
      <div className="flex min-h-0 flex-1 gap-4">
        {showList && listPane}
        {showEditor && editorPane}
      </div>

      <CreateEmailTemplateDialog
        open={creating}
        onOpenChange={setCreating}
        onCreated={(id) => navigate(`/emailtemplate/${id}`)}
      />

      {deleting && (
        <DeleteTemplateDialog
          template={deleting}
          open={!!deleting}
          onOpenChange={(v) => !v && setDeleting(null)}
          onDeleted={() => {
            if (selectedId === deleting.id) navigate("/emailtemplate")
            setDeleting(null)
          }}
        />
      )}
    </div>
  )
}
