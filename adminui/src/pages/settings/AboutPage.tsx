import { useState, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { GitBranch, Heart, Copy, Check, Calendar } from "lucide-react"

import { api } from "@/api/api.ts"
import { useBranding } from "@/hooks/use-branding"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/shadsnui/tooltip"
import { formatAppVersion } from "@/lib/version"

function GithubIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 1024 1024"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      {...props}
    >
      <title>GitHub</title>
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M8 0C3.58 0 0 3.58 0 8C0 11.54 2.29 14.53 5.47 15.59C5.87 15.66 6.02 15.42 6.02 15.21C6.02 15.02 6.01 14.39 6.01 13.72C4 14.09 3.48 13.23 3.32 12.78C3.23 12.55 2.84 11.84 2.5 11.65C2.22 11.5 1.82 11.13 2.49 11.12C3.12 11.11 3.57 11.7 3.72 11.94C4.44 13.15 5.59 12.81 6.05 12.6C6.12 12.08 6.33 11.73 6.56 11.53C4.78 11.33 2.92 10.64 2.92 7.58C2.92 6.71 3.23 5.99 3.74 5.43C3.66 5.23 3.38 4.41 3.82 3.31C3.82 3.31 4.49 3.1 6.02 4.13C6.66 3.95 7.34 3.86 8.02 3.86C8.7 3.86 9.38 3.95 10.02 4.13C11.55 3.09 12.22 3.31 12.22 3.31C12.66 4.41 12.38 5.23 12.3 5.43C12.81 5.99 13.12 6.7 13.12 7.58C13.12 10.65 11.25 11.33 9.47 11.53C9.76 11.78 10.01 12.26 10.01 13.01C10.01 14.08 10 14.94 10 15.21C10 15.42 10.15 15.67 10.55 15.59C13.71 14.53 16 11.53 16 8C16 3.58 12.42 0 8 0Z"
        transform="scale(64)"
        fill="currentColor"
      />
    </svg>
  )
}

function ForgejoIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      role="img"
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="#FB923C"
      xmlns="http://www.w3.org/2000/svg"
      {...props}
    >
      <title>Forgejo</title>
      <path d="M16.7773 0c1.6018 0 2.9004 1.2986 2.9004 2.9005s-1.2986 2.9004-2.9004 2.9004c-1.0854 0-2.0315-.596-2.5288-1.4787H12.91c-2.3322 0-4.2272 1.8718-4.2649 4.195l-.0007 2.1175a7.0759 7.0759 0 0 1 4.148-1.4205l.1176-.001 1.3385.0002c.4973-.8827 1.4434-1.4788 2.5288-1.4788 1.6018 0 2.9004 1.2986 2.9004 2.9005s-1.2986 2.9004-2.9004 2.9004c-1.0854 0-2.0315-.596-2.5288-1.4787H12.91c-2.3322 0-4.2272 1.8718-4.2649 4.195l-.0007 2.319c.8827.4973 1.4788 1.4434 1.4788 2.5287 0 1.602-1.2986 2.9005-2.9005 2.9005-1.6018 0-2.9004-1.2986-2.9004-2.9005 0-1.0853.596-2.0314 1.4788-2.5287l-.0002-9.9831c0-3.887 3.1195-7.0453 6.9915-7.108l.1176-.001h1.3385C14.7458.5962 15.692 0 16.7773 0ZM7.2227 19.9052c-.6596 0-1.1943.5347-1.1943 1.1943s.5347 1.1943 1.1943 1.1943 1.1944-.5347 1.1944-1.1943-.5348-1.1943-1.1944-1.1943Zm9.5546-10.4644c-.6596 0-1.1944.5347-1.1944 1.1943s.5348 1.1943 1.1944 1.1943c.6596 0 1.1943-.5347 1.1943-1.1943s-.5347-1.1943-1.1943-1.1943Zm0-7.7346c-.6596 0-1.1944.5347-1.1944 1.1943s.5348 1.1943 1.1944 1.1943c.6596 0 1.1943-.5347 1.1943-1.1943s-.5347-1.1943-1.1943-1.1943Z" />
    </svg>
  )
}

interface GithubRelease {
  tag_name: string
  name: string
  html_url: string
  draft: boolean
  prerelease: boolean
}

function formatBuildDate(rawDate: string): string {
  if (!rawDate || rawDate === "undefined") return "—"
  if (/^\d{2}\.\d{2}\.\d{4}$/.test(rawDate)) {
    return rawDate
  }
  try {
    const d = new Date(rawDate)
    if (isNaN(d.getTime())) return rawDate
    const pad = (n: number) => n.toString().padStart(2, "0")
    return `${pad(d.getUTCDate())}.${pad(d.getUTCMonth() + 1)}.${d.getUTCFullYear()}`
  } catch {
    return rawDate
  }
}

export function AboutPage() {
  const [copiedVersion, setCopiedVersion] = useState(false)
  const [copiedCommit, setCopiedCommit] = useState(false)

  const branding = useBranding()

  // Динамическое получение версии с бэкенда /api/health
  const { data: health } = useQuery({
    queryKey: ["app-health"],
    queryFn: async () => (await api.get<{ app_name: string; app_version: string }>("/health")).data,
    staleTime: 60_000,
  })

  // Динамические данные о коммите и дате сборки
  const appName = health?.app_name || (branding.name !== "SaviorBill Admin" ? branding.name : "SaviorBill")
  const rawVersion =
    health?.app_version || (typeof __APP_VERSION__ !== "undefined" && __APP_VERSION__ ? __APP_VERSION__ : "0.0.0-dev")
  const versionInfo = useMemo(() => formatAppVersion(rawVersion), [rawVersion])

  const effectiveCommit =
    typeof __GIT_COMMIT__ !== "undefined" && __GIT_COMMIT__ && __GIT_COMMIT__ !== "undefined"
      ? __GIT_COMMIT__
      : versionInfo.shortHash || "undefined"

  const shortCommit = useMemo(() => {
    if (!effectiveCommit || effectiveCommit === "undefined") return "undefined"
    return effectiveCommit.length > 8 ? effectiveCommit.slice(0, 7) : effectiveCommit
  }, [effectiveCommit])

  const gitDate = typeof __GIT_COMMIT_DATE__ !== "undefined" && __GIT_COMMIT_DATE__ ? __GIT_COMMIT_DATE__ : "undefined"
  const formattedDate = useMemo(() => formatBuildDate(gitDate), [gitDate])

  const handleCopyVersion = () => {
    navigator.clipboard.writeText(versionInfo.full).then(() => {
      setCopiedVersion(true)
      setTimeout(() => setCopiedVersion(false), 2000)
    })
  }

  const handleCopyCommit = () => {
    if (!effectiveCommit || effectiveCommit === "undefined") return
    navigator.clipboard.writeText(effectiveCommit).then(() => {
      setCopiedCommit(true)
      setTimeout(() => setCopiedCommit(false), 2000)
    })
  }

  // Проверка релизов через GitHub API (/releases возвращает 200 [] если релизов нет, без 404)
  const { data: releases } = useQuery({
    queryKey: ["github-releases"],
    queryFn: async () => {
      try {
        const res = await fetch("https://api.github.com/repos/UNVISLATE/SaviorBill/releases")
        if (!res.ok) return []
        return (await res.json()) as GithubRelease[]
      } catch {
        return []
      }
    },
    staleTime: 1000 * 60 * 60,
    retry: false,
  })

  const latestRelease = Array.isArray(releases) ? releases.find((r) => !r.draft) : undefined

  // Сравнение версий
  const isNewer = (latestTag?: string, currentVer?: string) => {
    if (!latestTag || !currentVer) return false
    const clean = (v: string) => v.replace(/^v/, "").trim()
    const c = clean(currentVer)
    const l = clean(latestTag)
    if (c === l) return false

    const [cBase] = c.split("-")
    const [lBase] = l.split("-")
    const cParts = cBase.split(".").map(Number)
    const lParts = lBase.split(".").map(Number)

    for (let i = 0; i < Math.max(cParts.length, lParts.length); i++) {
      const cp = cParts[i] || 0
      const lp = lParts[i] || 0
      if (lp > cp) return true
      if (lp < cp) return false
    }

    if (currentVer.includes("dev") || currentVer.includes("alpha") || currentVer.includes("beta")) {
      return true
    }
    return false
  }

  const hasUpdate = Boolean(latestRelease && isNewer(latestRelease.tag_name, versionInfo.base))

  return (
    <div className="flex h-[calc(100vh-13rem)] min-h-[420px] flex-col justify-between items-center overflow-hidden py-4 select-none">
      {/* Центр экрана: компактная аккуратная карточка SaviorBill */}
      <div className="flex-1 flex items-center justify-center w-full px-4">
        <div className="relative w-full max-w-md rounded-2xl border bg-card/95 p-6 sm:p-8 shadow-lg text-center flex flex-col items-center space-y-4 backdrop-blur-md">
          {/* Мягкое фоновое свечение */}
          <div className="pointer-events-none absolute -top-12 size-48 rounded-full bg-primary/10 blur-3xl" />

          {/* Логотип проекта SaviorBill */}
          <div className="relative size-16 rounded-2xl p-2.5 bg-muted/40 border border-border/80 shadow-xs flex items-center justify-center">
            <img
              src={branding.logoUrl || "/unvi/logo_1x1_128.webp"}
              alt={appName}
              className="size-full object-contain rounded-xl"
            />
          </div>

          {/* Заголовок + версия + статус latest/update */}
          <div className="flex items-center justify-center gap-2 flex-wrap">
            <h1 className="text-xl font-bold tracking-tight text-foreground">
              {appName}
            </h1>
            <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded-md bg-muted/60 border border-border/80 text-foreground">
              {versionInfo.base}
            </span>
            {hasUpdate && latestRelease ? (
              <a
                href={latestRelease.html_url}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-full bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 text-[10px] font-medium text-amber-500 hover:bg-amber-500/20 hover:text-amber-400 transition-colors flex items-center gap-1"
                title={`Доступна новая версия: ${latestRelease.tag_name}`}
              >
                <span className="size-1.5 rounded-full bg-amber-500 animate-pulse" />
                <span>{latestRelease.tag_name} ↗</span>
              </a>
            ) : (
              <span className="rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[10px] font-medium text-emerald-500 flex items-center gap-1">
                <span className="size-1.5 rounded-full bg-emerald-500" />
                latest
              </span>
            )}
          </div>

          {/* Хеш сборки (чистый компактный чип) */}
          {versionInfo.isExtended && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-muted/30 border border-border/70 max-w-full">
              <span className="text-[10px] uppercase font-semibold text-muted-foreground/60 tracking-wider shrink-0">
                Сборка:
              </span>
              <span
                className="font-mono text-[11px] text-muted-foreground truncate max-w-[220px] sm:max-w-[280px] select-all"
                title={versionInfo.full}
              >
                {versionInfo.full}
              </span>
              <button
                type="button"
                onClick={handleCopyVersion}
                className="text-muted-foreground/60 hover:text-foreground transition-colors p-0.5 shrink-0 cursor-pointer"
                title="Скопировать строку сборки"
                aria-label="Скопировать версию"
              >
                {copiedVersion ? (
                  <Check className="size-3 text-emerald-500" />
                ) : (
                  <Copy className="size-3" />
                )}
              </button>
            </div>
          )}

          {/* Описание проекта */}
          <p className="text-xs text-muted-foreground leading-relaxed max-w-sm text-balance">
            Событийная биллинг-система с изолированным исполнением через Lua, мультивалютным учётом и автоматизацией цифровых сервисов.
          </p>

          {hasUpdate && latestRelease && (
            <div className="flex items-center gap-1.5 text-[11px] text-amber-500/90 bg-amber-500/10 border border-amber-500/20 rounded-lg px-2.5 py-1">
              <span>Доступно обновление:</span>
              <a
                href={latestRelease.html_url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium underline hover:text-amber-400"
              >
                {latestRelease.tag_name}
              </a>
            </div>
          )}

          {/* Метаданные сборки: Commit и Дата в аккуратных бейджах */}
          <div className="flex flex-wrap items-center justify-center gap-2 pt-1">
            {/* Хеш коммита */}
            <Tooltip>
              <TooltipTrigger
                render={
                  <div className="flex items-center gap-1.5 rounded-lg border border-border/70 bg-muted/30 px-2.5 py-1 font-mono text-[11px] text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground">
                    <GitBranch className="size-3.5 text-primary shrink-0" />
                    <span className="text-muted-foreground/70">Commit:</span>
                    <span className="font-semibold text-foreground">{shortCommit}</span>
                    <button
                      type="button"
                      onClick={handleCopyCommit}
                      className="ml-0.5 text-muted-foreground/60 hover:text-foreground transition-colors cursor-pointer"
                      aria-label="Скопировать хеш коммита"
                    >
                      {copiedCommit ? (
                        <Check className="size-3 text-emerald-500" />
                      ) : (
                        <Copy className="size-3" />
                      )}
                    </button>
                  </div>
                }
              />
              <TooltipContent>
                {effectiveCommit !== "undefined"
                  ? `Полный коммит: ${effectiveCommit}`
                  : "Хеш коммита"}
              </TooltipContent>
            </Tooltip>

            {/* Дата сборки */}
            {formattedDate && formattedDate !== "undefined" && (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <div className="flex items-center gap-1.5 rounded-lg border border-border/70 bg-muted/30 px-2.5 py-1 font-mono text-[11px] text-muted-foreground">
                      <Calendar className="size-3.5 text-muted-foreground/70 shrink-0" />
                      <span className="text-muted-foreground/70">Дата:</span>
                      <span className="font-medium text-foreground">{formattedDate}</span>
                    </div>
                  }
                />
                <TooltipContent>
                  {gitDate !== "undefined" ? `Дата сборки: ${gitDate}` : "Дата коммита"}
                </TooltipContent>
              </Tooltip>
            )}
          </div>

          {/* Кастомные кнопки-ссылки с тултипом */}
          <div className="flex items-center justify-center gap-3 pt-2">
            {/* GitHub */}
            <Tooltip>
              <TooltipTrigger
                render={
                  <a
                    href="https://github.com/UNVISLATE/SaviorBill"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex size-10 items-center justify-center rounded-xl border border-border/80 bg-muted/30 hover:bg-muted text-muted-foreground hover:text-foreground transition-all hover:scale-105 active:scale-95 shadow-xs hover:border-primary/40 cursor-pointer"
                    aria-label="GitHub репозиторий"
                  >
                    <GithubIcon className="size-5" />
                  </a>
                }
              />
              <TooltipContent>GitHub репозиторий</TooltipContent>
            </Tooltip>

            {/* Git Зеркало */}
            <Tooltip>
              <TooltipTrigger
                render={
                  <a
                    href="https://git.unvi.xyz/UNVI/SaviorShop"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex size-10 items-center justify-center rounded-xl border border-border/80 bg-muted/30 hover:bg-muted text-muted-foreground hover:text-foreground transition-all hover:scale-105 active:scale-95 shadow-xs hover:border-primary/40 cursor-pointer"
                    aria-label="Git зеркало (Forgejo)"
                  >
                    <ForgejoIcon className="size-5" />
                  </a>
                }
              />
              <TooltipContent>Git зеркало (Forgejo)</TooltipContent>
            </Tooltip>

            {/* unvi.xyz */}
            <Tooltip>
              <TooltipTrigger
                render={
                  <a
                    href="https://unvi.xyz/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex size-10 items-center justify-center rounded-xl border border-border/80 bg-muted/30 hover:bg-muted text-muted-foreground hover:text-foreground transition-all hover:scale-105 active:scale-95 shadow-xs hover:border-primary/40 cursor-pointer"
                    aria-label="Сайт автора"
                  >
                    <img
                      src="/unvi/logo_1x1_128.webp"
                      alt="UNVI"
                      className="size-5 object-contain rounded"
                    />
                  </a>
                }
              />
              <TooltipContent>Сайт автора (unvi.xyz)</TooltipContent>
            </Tooltip>
          </div>
        </div>
      </div>

      {/* Внизу страницы */}
      <div className="text-xs text-muted-foreground text-center py-2 shrink-0">
        Made with{" "}
        <Heart className="size-3.5 text-red-500 fill-red-500 inline mx-0.5 animate-pulse" />{" "}
        by{" "}
        <a
          href="https://unvi.xyz/"
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-foreground hover:text-primary transition-colors underline decoration-muted-foreground/40 hover:decoration-primary"
        >
          Andrey UNVI
        </a>
      </div>
    </div>
  )
}
