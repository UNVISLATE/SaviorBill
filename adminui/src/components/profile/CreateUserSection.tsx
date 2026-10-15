import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Camera, ImagePlus, Trash2, UserRound } from "lucide-react"

import { api } from "@/api/api.ts"
import { getErrorDetail } from "@/lib/api-error.ts"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/shadsnui/avatar"
import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Label } from "@/components/shadsnui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import { MediaPickerDialog } from "@/components/media/MediaPickerDialog"
import { toastError, toastSuccess } from "@/lib/toast"

interface Role {
  id: number
  key: string
  name: string
}

interface MediaItem {
  id: number
  token: string
  kind: string
  url: string
}

export function CreateUserSection({
  onCreated,
  onCancel,
}: {
  section?: "profile" | "media"
  onCreated: (userId: number) => void
  onCancel: () => void
}) {
  const [login, setLogin] = useState("")
  const [password, setPassword] = useState("")
  const [email, setEmail] = useState("")
  const [roleId, setRoleId] = useState<string>("")
  const [avatar, setAvatar] = useState<MediaItem | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const qc = useQueryClient()

  const { data: roles } = useQuery({
    queryKey: ["admin-roles-lookup"],
    queryFn: async () => (await api.get<Role[]>("/v1/admin/roles")).data,
    staleTime: 5 * 60_000,
  })
  const assignable = roles?.filter((r) => r.key !== "owner") ?? []
  const selectedRole = assignable.find((r) => String(r.id) === String(roleId))

  const create = useMutation({
    mutationFn: async () =>
      (
        await api.post<{ id: number }>("/v1/admin/users", {
          login: login.trim(),
          password,
          email: email.trim() || undefined,
          role_id: roleId ? Number(roleId) : undefined,
          avatar_media_id: avatar?.id ?? null,
        })
      ).data,
    onSuccess: (res) => {
      toastSuccess(`Пользователь «${login.trim()}» создан`)
      void qc.invalidateQueries({ queryKey: ["admin-users"] })
      void qc.invalidateQueries({ queryKey: ["admin-users-stats"] })
      void qc.invalidateQueries({ queryKey: ["admin-users-stats-by-day"] })
      onCreated(res.id)
    },
    onError: (e: unknown) => {
      toastError("Не удалось создать пользователя", getErrorDetail(e))
    },
  })

  const isValid = login.trim().length >= 3 && password.length >= 8

  return (
    <div className="flex flex-col justify-between space-y-5">
      <div className="space-y-5">
        {/* Шапка 1-в-1 как в профиле: круглый аватар с кнопкой выбора + выбор роли рядом */}
        <div className="flex items-center gap-4">
          <div
            className="group relative size-16 shrink-0 cursor-pointer"
            onClick={() => setPickerOpen(true)}
            title="Выбрать аватар"
          >
            <Avatar className="size-16 ring-2 ring-border/50 transition-all group-hover:ring-primary">
              {avatar?.url && <AvatarImage src={avatar.url} alt={login} />}
              <AvatarFallback className="bg-muted text-lg font-semibold">
                {login.trim().slice(0, 2).toUpperCase() || (
                  <UserRound className="size-7 text-muted-foreground" />
                )}
              </AvatarFallback>
            </Avatar>
            <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40 opacity-0 transition-opacity group-hover:opacity-100">
              <Camera className="size-5 text-white" />
            </div>
            <span className="absolute -bottom-1 -right-1 flex size-5 items-center justify-center rounded-full border bg-background text-muted-foreground shadow-sm">
              <ImagePlus className="size-3" />
            </span>
          </div>

          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <Select value={roleId} onValueChange={(v) => setRoleId(v ?? "")}>
                <SelectTrigger id="create-role" size="sm" className="h-7 w-auto min-w-[130px] px-2 text-xs">
                  <SelectValue placeholder="Роль: user">
                    {selectedRole ? selectedRole.name : "Роль: user"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {assignable.map((r) => (
                    <SelectItem key={r.id} value={String(r.id)}>
                      {r.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {avatar && (
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  className="h-7 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive"
                  onClick={(e) => {
                    e.stopPropagation()
                    setAvatar(null)
                  }}
                >
                  <Trash2 className="mr-1 size-3" /> Удалить аватар
                </Button>
              )}
            </div>

            <p className="text-xs text-muted-foreground">
              {avatar
                ? "Аватар выбран из медиатеки"
                : "Нажмите на аватар для выбора картинки из медиатеки"}
            </p>
          </div>
        </div>

        {/* Поля ввода: 2 колонки (Логин и Email), затем Пароль */}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="create-login">Логин</Label>
            <Input
              id="create-login"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              placeholder="ivanov"
              autoFocus
            />
            <p className="text-[11px] text-muted-foreground">
              От 3 символов (латиница, кириллица, цифры)
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="create-email">Email (опционально)</Label>
            <Input
              id="create-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@example.com"
            />
            <p className="text-[11px] text-muted-foreground">
              Для уведомлений и сброса пароля
            </p>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="create-password">Пароль</Label>
          <Input
            id="create-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="минимум 8 символов"
          />
          <p className="text-[11px] text-muted-foreground">
            Минимум 8 символов
          </p>
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 border-t pt-4">
        <Button type="button" variant="outline" onClick={onCancel}>
          Отмена
        </Button>
        <Button
          type="button"
          disabled={!isValid || create.isPending}
          onClick={() => create.mutate()}
        >
          {create.isPending ? "Создание…" : "Создать пользователя"}
        </Button>
      </div>

      <MediaPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onSelect={(m) => {
          setAvatar(m)
          setPickerOpen(false)
        }}
      />
    </div>
  )
}
