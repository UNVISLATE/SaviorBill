import { ChevronsUpDown, LogOut, User as UserIcon } from "lucide-react"

import { useAuth } from "@/hooks/use-auth"
import { useProfileDialog } from "@/hooks/use-profile-dialog"
import { useUserProfile } from "@/hooks/use-user-profile"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/shadsnui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/shadsnui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/shadsnui/sidebar"

function initials(login: string): string {
  return login.slice(0, 2).toUpperCase()
}

/** Карточка текущего админа в подвале сайдбара (аватар + логин/роль → меню). */
export function NavUser() {
  const { me, logout } = useAuth()
  const { openProfile } = useProfileDialog()
  // AdminMe (useAuth) не содержит avatar_url — берём его из более полного
  // /v1/user/me, тот же запрос, что использует диалог профиля (общий кэш).
  const { data: profile } = useUserProfile()
  const { isMobile } = useSidebar()

  if (!me) return null

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <SidebarMenuButton size="lg">
                <Avatar className="size-8 rounded-lg">
                  {profile?.avatar_url && <AvatarImage src={profile.avatar_url} alt="" />}
                  <AvatarFallback className="rounded-lg">
                    {initials(me.login)}
                  </AvatarFallback>
                </Avatar>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium">{me.login}</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {me.role ?? "—"}
                  </span>
                </div>
                <ChevronsUpDown className="ml-auto size-4" />
              </SidebarMenuButton>
            }
          />
          <DropdownMenuContent
            className="w-(--anchor-width) min-w-56 rounded-lg"
            side={isMobile ? "bottom" : "right"}
            align="end"
          >
            {/* DropdownMenuLabel (Menu.GroupLabel) требует контекст Menu.Group —
                без него base-ui бросает "MenuGroupContext is missing" и валит
                всё дерево React (отсюда был эффект "весь дашборд чернеет"). */}
            <DropdownMenuGroup>
              <DropdownMenuLabel className="p-0 font-normal">
                <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                  <Avatar className="size-8 rounded-lg">
                    {profile?.avatar_url && <AvatarImage src={profile.avatar_url} alt="" />}
                    <AvatarFallback className="rounded-lg">
                      {initials(me.login)}
                    </AvatarFallback>
                  </Avatar>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-medium">{me.login}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {me.email ?? me.role ?? "—"}
                    </span>
                  </div>
                </div>
              </DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={openProfile}>
              <UserIcon />
              Профиль
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout}>
              <LogOut />
              Выйти
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
