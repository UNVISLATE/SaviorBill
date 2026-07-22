import { Navigate, Route, Routes } from "react-router-dom"
import { Activity, ListTodo, Server } from "lucide-react"

import { SectionTabs } from "@/components/layout/SectionTabs"
import { SystemOverview } from "./SystemOverview"
import { SystemInstances } from "./SystemInstances"
import { SystemTasks } from "./SystemTasks"

/** /system — мониторинг инстансов/потребления (см. IMPLEMENTATION_PLAN.md §2).
 * Live-графики строятся поллингом REST (last-N-points буфер на клиенте) —
 * решили не хранить историю метрик на backend. */
export function SystemPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Система</h1>
      <SectionTabs
        items={[
          { title: "Обзор", to: "/system/overview", icon: <Activity className="size-4" /> },
          { title: "Инстансы", to: "/system/instances", icon: <Server className="size-4" /> },
          { title: "Задачи", to: "/system/tasks", icon: <ListTodo className="size-4" /> },
        ]}
      >
        <Routes>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<SystemOverview />} />
          <Route path="instances" element={<SystemInstances />} />
          <Route path="tasks" element={<SystemTasks />} />
        </Routes>
      </SectionTabs>
    </div>
  )
}
