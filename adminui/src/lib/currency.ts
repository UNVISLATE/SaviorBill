import { useBranding } from "@/hooks/use-branding"

export const CURRENCY_SYMBOLS: Record<string, string> = {
  RUB: "₽",
  USD: "$",
  EUR: "€",
  GBP: "£",
  UAH: "₴",
  KZT: "₸",
  BYN: "Br",
  CNY: "¥",
  JPY: "¥",
  TRY: "₺",
  GEL: "₾",
  AMD: "֏",
  AZN: "₼",
  PLN: "zł",
  INR: "₹",
  THB: "฿",
  KGS: "с",
  UZS: "so'm",
  CAD: "C$",
  AUD: "A$",
}

export function getCurrencySymbol(code?: string | null): string {
  if (!code) return "₽"
  const upper = code.trim().toUpperCase()
  return CURRENCY_SYMBOLS[upper] ?? upper
}

export function formatMoney(
  amount: number | string | null | undefined,
  currency: string = "RUB"
): string {
  if (amount === null || amount === undefined || amount === "") return "—"
  const num = typeof amount === "number" ? amount : Number(amount)
  if (!Number.isFinite(num)) return String(amount)
  const sym = getCurrencySymbol(currency)
  const formatted = num.toLocaleString("ru-RU", {
    minimumFractionDigits: Number.isInteger(num) ? 0 : 2,
    maximumFractionDigits: 2,
  })
  return `${formatted} ${sym}`
}

export function useInstanceCurrency() {
  const branding = useBranding()
  const currency = (branding.currency || "RUB").toUpperCase()
  const symbol = getCurrencySymbol(currency)

  const format = (amount: number | string | null | undefined) => formatMoney(amount, currency)

  return {
    currency,
    symbol,
    formatMoney: format,
  }
}
