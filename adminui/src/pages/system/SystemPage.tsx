import { useMemo } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import {
  Activity,
  AlertTriangle,
  Bug,
  Clock,
  Database,
  ListTodo,
  Server,
  ShieldAlert,
} from "lucide-react"

import { useAuth } from "@/hooks/use-auth"
import { SectionTabs } from "@/components/layout/SectionTabs"
import { SystemOverview } from "./SystemOverview"
import { SystemInstances } from "./SystemInstances"
import { SystemTasks } from "./SystemTasks"
import { SystemTasksArchive } from "./SystemTasksArchive"
import { SystemDlq } from "./SystemDlq"
import { SystemCache } from "./SystemCache"
import { SystemSecurityEvents } from "./SystemSecurityEvents"
import { SystemErrorLogs } from "./SystemErrorLogs"

interface SystemTabDef {
  path: string
  title: string
  to: string
  icon: React.ReactNode
  element: React.ReactNode
  anyPerm?: string[]
}

const SYSTEM_TABS: SystemTabDef[] = [
  {
    path: "overview",
    title: "Обзор",
    to: "/system/overview",
    icon: <Activity className="size-4" />,
    element: <SystemOverview />,
    anyPerm: ["system.stats.read", "system.stats", "system"],
  },
  {
    path: "instances",
    title: "Инстансы",
    to: "/system/instances",
    icon: <Server className="size-4" />,
    element: <SystemInstances />,
    anyPerm: ["system.stats.read", "system.stats", "system"],
  },
  {
    path: "cache",
    title: "Кэш (Valkey)",
    to: "/system/cache",
    icon: <Database className="size-4" />,
    element: <SystemCache />,
    anyPerm: ["system.cache.read", "system.cache.manage", "system.cache", "system"],
  },
  {
    path: "security-events",
    title: "События безопасности",
    to: "/system/security-events",
    icon: <ShieldAlert className="size-4" />,
    element: <SystemSecurityEvents />,
    anyPerm: ["system.security.read", "system.security.manage", "system.security", "system"],
  },
  {
    path: "error-logs",
    title: "Журнал ошибок",
    to: "/system/error-logs",
    icon: <Bug className="size-4" />,
    element: <SystemErrorLogs />,
    anyPerm: ["system.errors.read", "system.errors", "system"],
  },
  {
    path: "tasks",
    title: "Задачи",
    to: "/system/tasks",
    icon: <ListTodo className="size-4" />,
    element: <SystemTasks />,
    anyPerm: ["system.tasks.summary.read", "system.tasks.tail.read", "system.tasks", "system"],
  },
  {
    path: "tasks/archive",
    title: "Архив задач",
    to: "/system/tasks/archive",
    icon: <Clock className="size-4" />,
    element: <SystemTasksArchive />,
    anyPerm: ["system.tasks.summary.read", "system.tasks.tail.read", "system.tasks", "system"],
  },
  {
    path: "dlq",
    title: "DLQ",
    to: "/system/dlq",
    icon: <AlertTriangle className="size-4" />,
    element: <SystemDlq />,
    anyPerm: ["system.tasks.dlq.read", "system.tasks.dlq.retry", "system.tasks.dlq", "system"],
  },
]

/** /system — мониторинг инстансов/потребления, кэша, безопасности и фоновых очередей задач.
 * Вкладки фильтруются строго по правам пользователя, с автоматическим редиректом на первую доступную. */
export function SystemPage() {
  const { can } = useAuth()

  const visibleTabs = useMemo(() => {
    return SYSTEM_TABS.filter((tab) => {
      if (!tab.anyPerm || tab.anyPerm.length === 0) return true
      return tab.anyPerm.some((p) => can(p))
    })
  }, [can])

  if (visibleTabs.length === 0) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold">Система</h1>
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          Недостаточно прав для просмотра раздела системы.
        </div>
      </div>
    )
  }

  const defaultTo = visibleTabs[0].to

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Система</h1>
      <SectionTabs items={visibleTabs}>
        <Routes>
          <Route index element={<Navigate to={defaultTo} replace />} />
          {visibleTabs.map((tab) => (
            <Route key={tab.path} path={tab.path} element={tab.element} />
          ))}
          <Route path="*" element={<Navigate to={defaultTo} replace />} />
        </Routes>
      </SectionTabs>
    </div>
  )
}
