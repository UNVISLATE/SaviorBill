import React from "react"
import { Check, Copy } from "lucide-react"

interface MarkdownPreviewProps {
  content: string
  className?: string
}

function parseMarkdownToHtml(markdown: string): string {
  if (!markdown) return ""

  // Escape HTML to prevent injection
  let html = markdown
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")

  // Code blocks (fenced)
  html = html.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<div class="sb-code-block my-3 rounded-lg overflow-hidden border border-border/70 bg-zinc-950/80 font-mono text-xs">
      ${lang ? `<div class="px-3 py-1 bg-zinc-900 border-b border-border/50 text-[10px] text-zinc-400 font-semibold tracking-wider uppercase">${lang}</div>` : ""}
      <pre class="p-3 overflow-x-auto text-zinc-200 leading-relaxed"><code>${code.trim()}</code></pre>
    </div>`
  })

  // Headers
  html = html.replace(/^#### (.*$)/gim, '<h4 class="text-xs font-semibold text-foreground mt-3 mb-1 uppercase tracking-wide">$1</h4>')
  html = html.replace(/^### (.*$)/gim, '<h3 class="text-sm font-semibold text-foreground mt-4 mb-1.5 flex items-center gap-1.5">$1</h3>')
  html = html.replace(/^## (.*$)/gim, '<h2 class="text-base font-semibold text-foreground mt-5 mb-2 border-b border-border/40 pb-1">$1</h2>')
  html = html.replace(/^# (.*$)/gim, '<h1 class="text-lg font-bold text-foreground mt-6 mb-2 border-b border-border/60 pb-1.5">$1</h1>')

  // Blockquotes
  html = html.replace(/^\> (.*$)/gim, '<blockquote class="border-l-2 border-primary/80 pl-3 py-1 my-2 text-xs text-muted-foreground bg-primary/5 rounded-r">$1</blockquote>')

  // Horizontal rules
  html = html.replace(/^---$/gim, '<hr class="my-4 border-border/60" />')

  // Bold & Italic
  html = html.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-foreground">$1</strong>')
  html = html.replace(/\*(.*?)\*/g, '<em class="italic text-foreground/90">$1</em>')
  html = html.replace(/~~(.*?)~~/g, '<del class="line-through text-muted-foreground">$1</del>')

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 rounded bg-muted/60 font-mono text-[11px] text-primary font-medium">$1</code>')

  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-primary underline hover:text-primary/80 font-medium">$1</a>')

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
        trimmed.startsWith("<li")
      ) {
        return trimmed
      }
      return `<p class="my-2 leading-relaxed">${trimmed.replace(/\n/g, "<br/>")}</p>`
    })
    .join("\n")

  return html
}

export function MarkdownPreview({ content, className = "" }: MarkdownPreviewProps) {
  const [copied, setCopied] = React.useState(false)
  const html = React.useMemo(() => parseMarkdownToHtml(content), [content])

  const copyToClipboard = () => {
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (!content || !content.trim()) {
    return (
      <div className={`p-6 text-center text-xs text-muted-foreground border border-dashed rounded-lg ${className}`}>
        Инструкция в формате Markdown пуста
      </div>
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
