import { Component, type ErrorInfo, type ReactNode } from "react"
import { AlertTriangle, RefreshCw, Home, RotateCcw } from "lucide-react"
import { Button } from "@/components/shadsnui/button"

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode | ((error: Error, reset: () => void) => ReactNode)
  onReset?: () => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught an unhandled error:", error, errorInfo)
  }

  reset = () => {
    this.props.onReset?.()
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (typeof this.props.fallback === "function") {
        return this.props.fallback(this.state.error ?? new Error("Unknown error"), this.reset)
      }
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="flex min-h-[360px] w-full flex-col items-center justify-center rounded-2xl border border-destructive/20 bg-destructive/5 p-8 text-center animate-in fade-in-50">
          <div className="flex size-14 items-center justify-center rounded-2xl bg-destructive/15 text-destructive mb-4 shadow-xs">
            <AlertTriangle className="size-7" />
          </div>
          <h2 className="text-lg font-semibold tracking-tight text-foreground">
            Произошла непредвиденная ошибка
          </h2>
          <p className="mt-1.5 max-w-md text-sm text-muted-foreground">
            {this.state.error?.message || "Не удалось отобразить этот раздел интерфейса."}
          </p>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <Button size="sm" onClick={this.reset} className="gap-1.5">
              <RotateCcw className="size-3.5" />
              Попробовать снова
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                window.location.href = "/"
              }}
              className="gap-1.5"
            >
              <Home className="size-3.5" />
              На главную
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                window.location.reload()
              }}
              className="gap-1.5 text-muted-foreground"
            >
              <RefreshCw className="size-3.5" />
              Перезагрузить
            </Button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
