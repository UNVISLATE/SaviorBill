import { toast } from "sonner"

/** Единая точка для toast-уведомлений (см. IMPLEMENTATION_PLAN.md §0.2) —
 * не дублируем настройку позиции/стилей в каждом месте вызова. */
export function toastSuccess(message: string, description?: string) {
  toast.success(message, { description })
}

export function toastError(message: string, description?: string) {
  toast.error(message, { description })
}

export function toastInfo(message: string, description?: string) {
  toast.info(message, { description })
}
