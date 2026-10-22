import { useState } from "react"
import { Check, Copy, ExternalLink, QrCode } from "lucide-react"
import { Button } from "@/components/shadsnui/button"
import { Badge } from "@/components/shadsnui/badge"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/shadsnui/popover"
import { toastSuccess } from "@/lib/toast"

interface DataPropertySheetProps {
  data: Record<string, unknown> | null | undefined
  title?: string
  emptyText?: string
  className?: string
}

function isUrl(val: string): boolean {
  return /^https?:\/\//i.test(val)
}

function isConfigString(val: string): boolean {
  return /^(vless|vmess|ss|trojan|wireguard|wg):\/\//i.test(val)
}

function ValueRenderer({ value }: { value: unknown }) {
  const [copied, setCopied] = useState(false)

  const copyVal = (text: string) => {
    void navigator.clipboard.writeText(text)
    setCopied(true)
    toastSuccess("Скопировано в буфер")
    setTimeout(() => setCopied(false), 2000)
  }

  if (value === null || value === undefined) {
    return <span className="text-muted-foreground/60 italic text-xs">null</span>
  }

  if (typeof value === "boolean") {
    return (
      <Badge variant={value ? "default" : "outline"} className="text-xs">
        {value ? "true" : "false"}
      </Badge>
    )
  }

  if (typeof value === "number") {
    return <span className="font-mono text-xs font-semibold text-emerald-400">{value}</span>
  }

  if (typeof value === "string") {
    if (isUrl(value)) {
      return (
        <div className="flex items-center gap-2 max-w-full">
          <a
            href={value}
            target="_blank"
            rel="noopener noreferrer"
            className="truncate text-xs text-primary underline underline-offset-4 hover:text-primary/80 flex items-center gap-1"
          >
            <span className="truncate">{value}</span>
            <ExternalLink className="size-3 shrink-0" />
          </a>
          <Button
            size="icon"
            variant="ghost"
            className="size-6 shrink-0"
            onClick={() => copyVal(value)}
            title="Скопировать ссылку"
          >
            {copied ? <Check className="size-3 text-emerald-400" /> : <Copy className="size-3" />}
          </Button>
        </div>
      )
    }

    if (isConfigString(value)) {
      return (
        <div className="space-y-1.5 w-full">
          <div className="flex items-center gap-1.5">
            <code className="flex-1 truncate rounded bg-muted/60 px-2 py-1 font-mono text-[11px] select-all border border-border/60">
              {value}
            </code>
            <Button
              size="icon"
              variant="outline"
              className="size-7 shrink-0"
              onClick={() => copyVal(value)}
              title="Скопировать конфиг"
            >
              {copied ? <Check className="size-3.5 text-emerald-400" /> : <Copy className="size-3.5" />}
            </Button>
            <Popover>
              <PopoverTrigger render={<Button size="icon" variant="outline" className="size-7 shrink-0" title="QR-код" />}>
                <QrCode className="size-3.5" />
              </PopoverTrigger>
              <PopoverContent className="w-auto p-4 flex flex-col items-center gap-2">
                <img
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(value)}`}
                  alt="QR Code"
                  className="size-44 rounded-md bg-white p-1"
                />
                <span className="text-[11px] text-muted-foreground">Сканируйте приложением</span>
              </PopoverContent>
            </Popover>
          </div>
        </div>
      )
    }

    return (
      <div className="flex items-center justify-between gap-2 max-w-full">
        <span className="font-mono text-xs break-all select-all">{value}</span>
        {value.length > 3 && (
          <Button
            size="icon"
            variant="ghost"
            className="size-6 shrink-0 opacity-70 hover:opacity-100"
            onClick={() => copyVal(value)}
            title="Скопировать"
          >
            {copied ? <Check className="size-3 text-emerald-400" /> : <Copy className="size-3" />}
          </Button>
        )}
      </div>
    )
  }

  if (typeof value === "object") {
    const jsonStr = JSON.stringify(value, null, 2)
    return (
      <div className="relative group w-full">
        <pre className="max-h-40 overflow-auto rounded-lg bg-muted/40 p-2.5 font-mono text-[11px] border border-border/60">
          {jsonStr}
        </pre>
        <Button
          size="icon"
          variant="outline"
          className="absolute right-2 top-2 size-6 opacity-0 group-hover:opacity-100 transition-opacity bg-background/80 shadow-xs"
          onClick={() => copyVal(jsonStr)}
          title="Скопировать объект"
        >
          {copied ? <Check className="size-3 text-emerald-400" /> : <Copy className="size-3" />}
        </Button>
      </div>
    )
  }

  return <span className="text-xs">{String(value)}</span>
}

export function DataPropertySheet({
  data,
  title,
  emptyText = "Данные отсутствуют",
  className,
}: DataPropertySheetProps) {
  const [copiedAll, setCopiedAll] = useState(false)

  const entries = data && typeof data === "object" ? Object.entries(data) : []

  const copyAll = () => {
    if (!data) return
    void navigator.clipboard.writeText(JSON.stringify(data, null, 2))
    setCopiedAll(true)
    toastSuccess("Весь JSON скопирован")
    setTimeout(() => setCopiedAll(false), 2000)
  }

  return (
    <div className={`rounded-xl border border-border/80 bg-card/60 p-3.5 space-y-3 ${className ?? ""}`}>
      <div className="flex items-center justify-between">
        {title && <span className="text-xs font-medium text-muted-foreground">{title}</span>}
        {entries.length > 0 && (
          <Button
            size="xs"
            variant="ghost"
            className="h-6 gap-1.5 text-[11px] text-muted-foreground hover:text-foreground ml-auto"
            onClick={copyAll}
          >
            {copiedAll ? <Check className="size-3 text-emerald-400" /> : <Copy className="size-3" />}
            <span>Скопировать JSON</span>
          </Button>
        )}
      </div>

      {entries.length === 0 ? (
        <div className="py-4 text-center text-xs text-muted-foreground/60 italic">
          {emptyText}
        </div>
      ) : (
        <div className="divide-y divide-border/40">
          {entries.map(([key, val]) => (
            <div key={key} className="py-2 first:pt-0 last:pb-0 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
              <span className="font-mono text-xs text-muted-foreground shrink-0 min-w-28 font-medium">
                {key}
              </span>
              <div className="flex-1 min-w-0">
                <ValueRenderer value={val} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
