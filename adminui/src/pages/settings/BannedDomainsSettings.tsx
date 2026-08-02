import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Ban, Plus, Trash2 } from "lucide-react"

import { api } from "@/api/api.ts"
import { useAuth } from "@/hooks/use-auth"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/shadsnui/card"
import {
  Dialog,
  DialogContent,
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
import { toastError, toastSuccess } from "@/lib/toast"

interface BannedDomain {
  domain: string
  reason: string | null
  created_at: string
}

function errDetail(e: unknown): string | undefined {
  if (e && typeof e === "object" && "response" in e) {
    // @ts-expect-error — axios error shape
    const d = e.response?.data?.detail
    return typeof d === "string" ? d : undefined
  }
  return undefined
}

function AddDomainDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [domain, setDomain] = useState("")
  const [reason, setReason] = useState("")
  const qc = useQueryClient()

  const reset = () => {
    setDomain("")
    setReason("")
  }

  const add = useMutation({
    mutationFn: async () => api.post("/v1/admin/settings/email-domains", { domain, reason: reason || null }),
    onSuccess: () => {
      toastSuccess(`Домен «${domain}» заблокирован`)
      onOpenChange(false)
      reset()
      void qc.invalidateQueries({ queryKey: ["admin-banned-domains"] })
    },
    onError: (e: unknown) => toastError("Не удалось добавить домен", errDetail(e)),
  })

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Заблокировать домен</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Домен</Label>
            <Input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="tempmail.com" autoFocus />
          </div>
          <div className="space-y-1">
            <Label>Причина (опционально)</Label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="временная почта" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button disabled={domain.trim().length < 1 || add.isPending} onClick={() => add.mutate()}>
            Заблокировать
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Заблокированные для регистрации email-домены — попытка зарегистрироваться
 * с почтой на таком домене отклоняется на бэкенде (защита от временной
 * почты/спама). Список маленький — без пагинации, простая таблица. */
export function BannedDomainsSettings() {
  const { can } = useAuth()
  const [adding, setAdding] = useState(false)
  const canEdit = can("settings.email_domains.edit")
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["admin-banned-domains"],
    queryFn: async () => (await api.get<BannedDomain[]>("/v1/admin/settings/email-domains")).data,
  })

  const remove = useMutation({
    mutationFn: async (domain: string) => api.delete(`/v1/admin/settings/email-domains/${encodeURIComponent(domain)}`),
    onSuccess: () => {
      toastSuccess("Домен разблокирован")
      void qc.invalidateQueries({ queryKey: ["admin-banned-domains"] })
    },
    onError: (e: unknown) => toastError("Не удалось разблокировать домен", errDetail(e)),
  })

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Заблокированные почтовые домены</CardTitle>
          <CardDescription>Регистрация с почтой на этих доменах отклоняется.</CardDescription>
        </div>
        {canEdit && (
          <Button size="sm" onClick={() => setAdding(true)}>
            <Plus className="size-4" /> Добавить
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
        {!isLoading && (data?.length ?? 0) === 0 && (
          <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
            <Ban className="size-6" />
            Заблокированных доменов нет.
          </div>
        )}
        {!isLoading && (data?.length ?? 0) > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Домен</TableHead>
                <TableHead>Причина</TableHead>
                <TableHead>Добавлен</TableHead>
                {canEdit && <TableHead className="text-right">Действия</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.map((d) => (
                <TableRow key={d.domain}>
                  <TableCell className="font-mono text-xs">{d.domain}</TableCell>
                  <TableCell className="text-muted-foreground">{d.reason ?? "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(d.created_at).toLocaleDateString()}
                  </TableCell>
                  {canEdit && (
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8 text-destructive"
                        onClick={() => remove.mutate(d.domain)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      <AddDomainDialog open={adding} onOpenChange={setAdding} />
    </Card>
  )
}
