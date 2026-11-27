import React from "react"
import { Check, Copy } from "lucide-react"

interface MarkdownPreviewProps {
  content: string
  className?: string
  bare?: boolean
}

function sanitizeUrl(rawUrl: string): string {
  const trimmed = rawUrl.trim()
  if (/^(https?:|mailto:|\/(?![/\\]))/i.test(trimmed) || trimmed === "/") {
    return trimmed.replace(/"/g, "&quot;").replace(/'/g, "&#39;")
  }
  return "#"
}

function parseMarkdownToHtml(markdown: string): string {
  if (!markdown) return ""

  // Extract code blocks (fenced) prior to HTML escaping and formatting
  const codeBlocks: string[] = []
  let html = markdown
    .replace(/\r\n/g, "\n")
    .replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (_, lang, code) => {
      const idx = codeBlocks.length
      const escapedCode = code
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .trim()
      codeBlocks.push(
        `<div class="sb-code-block my-3 rounded-lg overflow-hidden border border-border/70 bg-zinc-950/80 font-mono text-xs">
          ${lang ? `<div class="px-3 py-1 bg-zinc-900 border-b border-border/50 text-[10px] text-zinc-400 font-semibold tracking-wider uppercase">${lang}</div>` : ""}
          <pre class="p-3 overflow-x-auto text-zinc-200 leading-relaxed"><code>${escapedCode}</code></pre>
        </div>`
      )
      return `___CODE_BLOCK_${idx}___`
    })

  // Escape HTML on remainder to prevent injection
  html = html
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")

  // Support 2+ trailing spaces or a backslash at line end as hard line break (AFTER HTML escape!)
  html = html.replace(/( {2,}|\\)\n/g, "<br/>")

  // Ensure headings and dividers have clean paragraph boundaries
  html = html.replace(/^(#{1,4}\s+.*$)/gm, "\n\n$1\n\n")
  html = html.replace(/^(---\s*$)/gm, "\n\n$1\n\n")

  // Headers
  html = html.replace(/^#### (.*$)/gim, '<h4 class="text-xs font-semibold text-foreground mt-3 mb-1 uppercase tracking-wide">$1</h4>')
  html = html.replace(/^### (.*$)/gim, '<h3 class="text-sm font-semibold text-foreground mt-4 mb-1.5 flex items-center gap-1.5">$1</h3>')
  html = html.replace(/^## (.*$)/gim, '<h2 class="text-base font-semibold text-foreground mt-5 mb-2 border-b border-border/40 pb-1">$1</h2>')
  html = html.replace(/^# (.*$)/gim, '<h1 class="text-lg font-bold text-foreground mt-6 mb-2 border-b border-border/60 pb-1.5">$1</h1>')

  // Blockquotes
  html = html.replace(/^> (.*$)/gim, '<blockquote class="border-l-2 border-primary/80 pl-3 py-1 my-2 text-xs text-muted-foreground bg-primary/5 rounded-r">$1</blockquote>')

  // Horizontal rules
  html = html.replace(/^---$/gim, '<hr class="my-4 border-border/60" />')

  // Bold & Italic
  html = html.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-foreground">$1</strong>')
  html = html.replace(/\*(.*?)\*/g, '<em class="italic text-foreground/90">$1</em>')
  html = html.replace(/~~(.*?)~~/g, '<del class="line-through text-muted-foreground">$1</del>')

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 rounded bg-muted/60 font-mono text-[11px] text-primary font-medium">$1</code>')

  // Images: ![alt](url) -> MUST be processed before links [label](url)
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, url) => {
    const safeUrl = sanitizeUrl(url)
    return `<div class="my-3"><img src="${safeUrl}" alt="${alt || ""}" class="max-w-full h-auto rounded-lg border border-border/50 object-cover shadow-2xs" loading="lazy" /></div>`
  })

  // Links with safe URL sanitization
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, url) => {
    const safeUrl = sanitizeUrl(url)
    return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="text-primary underline underline-offset-2 hover:text-primary/80 font-medium">${label}</a>`
  })

  // Unordered list items
  html = html.replace(/^\s*[-*]\s+\[ \]\s+(.*$)/gim, '<li class="flex items-center gap-2 list-none my-1"><span class="size-3.5 rounded border border-border flex items-center justify-center text-[10px]"></span><span>$1</span></li>')
  html = html.replace(/^\s*[-*]\s+\[x\]\s+(.*$)/gim, '<li class="flex items-center gap-2 list-none my-1 text-muted-foreground"><span class="size-3.5 rounded bg-primary text-primary-foreground flex items-center justify-center text-[10px]">✓</span><span class="line-through">$1</span></li>')
  html = html.replace(/^\s*[-*]\s+(.*$)/gim, '<li class="list-disc ml-5 my-0.5">$1</li>')

  // Ordered list items
  html = html.replace(/^\s*\d+\.\s+(.*$)/gim, '<li class="list-decimal ml-5 my-0.5">$1</li>')

  // Paragraphs (lines separated by double newline)
  const paragraphs = html.split(/\n{2,}/)
  html = paragraphs
    .map((p) => {
      const trimmed = p.trim()
      if (!trimmed) return ""
      if (
        trimmed.startsWith("<h") ||
        trimmed.startsWith("<div") ||
        trimmed.startsWith("<blockquote") ||
        trimmed.startsWith("<hr") ||
        trimmed.startsWith("<li") ||
        trimmed.startsWith("___CODE_BLOCK_")
      ) {
        return trimmed
      }
      return `<p class="my-2 leading-relaxed">${trimmed.replace(/\n/g, " ")}</p>`
    })
    .join("\n")

  // Restore code blocks
  html = html.replace(/___CODE_BLOCK_(\d+)___/g, (_, idxStr) => {
    const idx = Number(idxStr)
    return codeBlocks[idx] ?? ""
  })

  return html
}

export function MarkdownPreview({ content, className = "", bare = false }: MarkdownPreviewProps) {
  const [copied, setCopied] = React.useState(false)
  const html = React.useMemo(() => parseMarkdownToHtml(content), [content])

  const copyToClipboard = () => {
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (!content || !content.trim()) {
    if (bare) {
      return null
    }
    return (
      <div className={`p-6 text-center text-xs text-muted-foreground border border-dashed rounded-lg ${className}`}>
        Инструкция в формате Markdown пуста
      </div>
    )
  }

  if (bare) {
    return (
      <div
        className={`sb-markdown-content leading-relaxed text-sm text-foreground/90 ${className}`}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    )
  }

  return (
    <div className={`relative rounded-lg border border-border/80 bg-card/60 p-4 text-xs text-foreground/90 ${className}`}>
      <button
        type="button"
        onClick={copyToClipboard}
        className="absolute top-2.5 right-2.5 p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
        title="Скопировать Markdown"
      >
        {copied ? <Check className="size-3.5 text-emerald-500" /> : <Copy className="size-3.5" />}
      </button>
      <div
        className="sb-markdown-content leading-relaxed"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  )
}
