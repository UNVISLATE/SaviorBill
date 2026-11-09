import { Button } from "@/components/shadsnui/button"
import { Input } from "@/components/shadsnui/input"
import { Badge } from "@/components/shadsnui/badge"
import { Switch } from "@/components/shadsnui/switch"
import { Label } from "@/components/shadsnui/label"
import { Textarea } from "@/components/shadsnui/textarea"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
} from "@/components/shadsnui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/shadsnui/select"
import { DeclarativeForm } from "@/components/common/forms/DeclarativeForm"
import { KeySecretEditor } from "@/components/common/forms/KeySecretEditor"
import { toast } from "sonner"
import { api } from "@/api/api"

export function setupSaviorUI() {
  if (typeof window === "undefined") return

  // Экспортируем Host UI-Kit для микро-фронтендов плагинов
  ;(window as any).SaviorUI = {
    Button,
    Input,
    Badge,
    Switch,
    Label,
    Textarea,
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
    DialogTrigger,
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
    DeclarativeForm,
    KeySecretEditor,
    toast,
    api,
  }
}
