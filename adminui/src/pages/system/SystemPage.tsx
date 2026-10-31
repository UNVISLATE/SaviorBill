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
  group?: string
  hint?: string
  anyPerm?: string[]
}

const SYSTEM_TABS: SystemTabDef[] = [
  // Группа 1: Обзор
  {
    path: "overview",
    title: "Обзор",
    to: "/system/overview",
    icon: <Activity className="size-4" />,
    element: <SystemOverview />,
    group: "Обзор",
    anyPerm: ["system.stats.read", "system.stats", "system"],
  },
  {
    path: "instances",
    title: "Инстансы",
    to: "/system/instances",
    icon: <Server className="size-4" />,
    element: <SystemInstances />,
    group: "Обзор",
    anyPerm: ["system.stats.read", "system.stats", "system"],
  },
  {
    path: "cache",
    title: "Кэш",
    to: "/system/cache",
    icon: <Database className="size-4" />,
    element: <SystemCache />,
    group: "Обзор",
    anyPerm: ["system.cache.read", "system.cache.manage", "system.cache", "system"],
  },

  // Группа 2: Безопасность
  {
    path: "security-events",
    title: "Безопасность",
    to: "/system/security-events",
    icon: <ShieldAlert className="size-4" />,
    element: <SystemSecurityEvents />,
    group: "Безопасность",
    anyPerm: ["system.security.read", "system.security.manage", "system.security", "system"],
  },
  {
    path: "error-logs",
    title: "Журнал ошибок",
    to: "/system/error-logs",
    icon: <Bug className="size-4" />,
    element: <SystemErrorLogs />,
    group: "Безопасность",
    anyPerm: ["system.errors.read", "system.errors", "system"],
  },

  // Группа 3: Задачи
  {
    path: "tasks",
    title: "Задачи",
    to: "/system/tasks",
    icon: <ListTodo className="size-4" />,
    element: <SystemTasks />,
    group: "Задачи",
    anyPerm: ["system.tasks.summary.read", "system.tasks.tail.read", "system.tasks", "system"],
  },
  {
    path: "tasks/archive",
    title: "Архив",
    to: "/system/tasks/archive",
    icon: <Clock className="size-4" />,
    element: <SystemTasksArchive />,
    group: "Задачи",
    anyPerm: ["system.tasks.summary.read", "system.tasks.tail.read", "system.tasks", "system"],
  },
  {
    path: "dlq",
    title: "DLQ",
    to: "/system/dlq",
    icon: <AlertTriangle className="size-4" />,
    element: <SystemDlq />,
    group: "Задачи",
    hint: "Очередь Dead Letter Queue: отложенные задачи, завершившиеся ошибкой после всех повторных попыток",
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

  const tabItems = useMemo(() => {
    return visibleTabs.map((tab) => ({
      title: tab.title,
      to: tab.to,
      icon: tab.icon,
      group: tab.group,
      hint: tab.hint,
    }))
  }, [visibleTabs])

  if (visibleTabs.length === 0) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        У вас нет прав для просмотра разделов мониторинга системы.
      </div>
    )
  }

  const defaultRedirect = visibleTabs[0]?.path ?? "overview"

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Система</h1>
        <p className="text-sm text-muted-foreground">
          Управление инстансами, мониторинг кэша Valkey, журнал безопасности и фоновые очереди задач.
        </p>
      </div>

      <SectionTabs items={tabItems}>
        <Routes>
          <Route path="/" element={<Navigate to={defaultRedirect} replace />} />
          {visibleTabs.map((tab) => (
            <Route key={tab.path} path={tab.path} element={tab.element} />
          ))}
          <Route path="*" element={<Navigate to={defaultRedirect} replace />} />
        </Routes>
      </SectionTabs>
    </div>
  )
}
