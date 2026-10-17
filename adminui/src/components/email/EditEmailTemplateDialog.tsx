import { useState, useEffect } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { toastError, toastSuccess } from "@/lib/toast"
import { Button } from "@/components/shadsnui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/shadsnui/dialog"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Textarea } from "@/components/shadsnui/textarea"

export function EditEmailTemplateDialog({
  open,
  onOpenChange,
  template,
  onUpdated,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  template: {
    id: number
    slug: string
    name: string | null
    description?: string | null
  }
  onUpdated?: (name: string, description?: string) => void
}) {
  const qc = useQueryClient()
  const [name, setName] = useState(template.name ?? "")
  const [description, setDescription] = useState(template.description ?? "")

  useEffect(() => {
    if (open) {
      setName(template.name ?? "")
      setDescription(template.description ?? "")
    }
  }, [open, template])

  const save = useMutation({
    mutationFn: async () => {
      return (
        await api.patch<{ id: number; name: string | null; description?: string | null }>(
          `/v1/admin/email/templates/${template.id}`,
          {
            name: name.trim() || null,
            description: description.trim() || null,
          },
        )
      ).data
    },
    onSuccess: (updated) => {
      toastSuccess("Информация обновлена")
      void qc.invalidateQueries({ queryKey: ["admin-email-templates"] })
      void qc.invalidateQueries({ queryKey: ["admin-email-template-detail", template.id] })
      onUpdated?.(updated.name ?? "", updated.description ?? undefined)
      onOpenChange(false)
    },
    onError: (err: unknown) => {
      toastError("Не удалось обновить шаблон", getErrorDetail(err))
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Редактировать параметры шаблона</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1">
            <Label>Слаг</Label>
            <Input value={template.slug} disabled className="font-mono text-sm bg-muted/40" />
            <p className="text-[11px] text-muted-foreground">
              Слаг шаблона фиксирован и не может быть изменён
            </p>
          </div>

          <div className="space-y-1">
            <Label htmlFor="edit-tpl-name">Название</Label>
            <Input
              id="edit-tpl-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Название шаблона"
              autoFocus
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="edit-tpl-desc">Описание (опционально)</Label>
            <Textarea
              id="edit-tpl-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Для чего используется шаблон..."
              rows={3}
              className="text-xs"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Сохранение…" : "Сохранить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
