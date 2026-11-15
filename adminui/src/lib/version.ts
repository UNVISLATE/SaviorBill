export interface AppVersionInfo {
  full: string
  base: string
  shortHash: string | null
  short: string
  isExtended: boolean
}

export function formatAppVersion(raw: string | undefined | null): AppVersionInfo {
  const normalized = (raw || "0.0.0-dev").trim()
  const full = normalized.startsWith("v") ? normalized : `v${normalized}`

  // SemVer base tag (e.g., "v1.0.0", "v1.2.3", "v0.1.0")
  const baseMatch = full.match(/^(v?\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9.]+)?)/)
  let base = baseMatch ? baseMatch[1] : full

  // Clean trailing dev/hash indicators from base if present (e.g., "v1.0.0.dev17" -> "v1.0.0")
  base = base.replace(/(\.dev\d+|\.post\d+).*$/, "")

  // Extract git hash if present: "+ge9df0948", "-ge9df0948", "-e9df0948", or any 7-40 hex chars
  const hashMatch =
    full.match(/[+.-]g?([0-9a-f]{7,40})\b/i) ||
    full.match(/[-+]([0-9a-f]{7,12})\b/i)
  const shortHash = hashMatch ? hashMatch[1].slice(0, 7) : null

  // Check if version has long build or hash metadata
  const isExtended = full.length > 14 || Boolean(shortHash) || full.includes("+") || full.includes("-")

  let short = full
  if (isExtended) {
    if (shortHash) {
      short = `${base} (${shortHash})`
    } else {
      // If there's an alphanumeric suffix after - or +
      const suffixMatch = full.match(/[-+]([a-zA-Z0-9_-]+)$/)
      if (suffixMatch && suffixMatch[1].length > 7) {
        short = `${base} (${suffixMatch[1].slice(0, 7)})`
      } else if (suffixMatch) {
        short = `${base} (${suffixMatch[1]})`
      } else {
        short = `${base}+`
      }
    }
  }

  // Ensure button short text never exceeds 20 characters
  if (short.length > 20) {
    short = short.slice(0, 18) + "…"
  }

  return { full, base, shortHash, short, isExtended }
}
