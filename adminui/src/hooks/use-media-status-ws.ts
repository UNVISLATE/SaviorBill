import { useEffect, useRef, useState } from "react"

import { getAccessToken } from "@/lib/tokens"

/** Снимок статуса конвертации одного media-токена (см. mediaworker ProcLog). */
export interface MediaStatusSnap {
  state?: string
  percent?: string
  eta_sec?: string
  error?: string
}

/**
 * Живой статус конкретных media-токенов через ``/api/media/mine``
 * (mediaworker — единственный писатель этого статуса, см. IMPLEMENTATION_PLAN.md §3).
 *
 * Раньше каждая карточка в обработке опрашивала REST-статус по таймеру —
 * при нескольких параллельных загрузках это N HTTP-запросов с клиента,
 * плюс лишняя нагрузка на mediaworker, когда он занят конвертацией. Здесь
 * один WS на все токены сразу; соединение открывается только пока есть за
 * чем следить (``tokens`` не пуст) и закрывается сервером само, как только
 * все они дошли до готового/ошибочного состояния (``{"type": "idle"}``).
 *
 * Новые токены (например, докинули ещё файлов, пока соединение уже открыто)
 * добавляются в него же доп. фреймом — без переоткрытия WS.
 */
export function useMediaStatusStream(tokens: string[]): Record<string, MediaStatusSnap> {
  const [statuses, setStatuses] = useState<Record<string, MediaStatusSnap>>({})
  const wsRef = useRef<WebSocket | null>(null)
  const watchedRef = useRef<Set<string>>(new Set())
  const active = tokens.length > 0

  // Открыть соединение при появлении первого токена, закрыть, когда следить
  // больше не за чем. Список последующих токенов шлём отдельным эффектом
  // ниже — не пересоздавая сам сокет на каждое изменение.
  useEffect(() => {
    if (!active) {
      watchedRef.current = new Set()
      return
    }
    const accessToken = getAccessToken()
    if (!accessToken) return

    const proto = location.protocol === "https:" ? "wss" : "ws"
    const ws = new WebSocket(`${proto}://${location.host}/api/media/mine`)
    wsRef.current = ws

    ws.onopen = () => {
      watchedRef.current = new Set(tokens)
      ws.send(JSON.stringify({ token: accessToken, watch: tokens }))
    }
    ws.onmessage = (ev) => {
      let msg: { type: string; items?: Record<string, MediaStatusSnap> }
      try {
        msg = JSON.parse(ev.data)
      } catch {
        return
      }
      if (msg.type === "status" && msg.items) {
        setStatuses((prev) => ({ ...prev, ...msg.items }))
      } else if (msg.type === "idle" || msg.type === "timeout") {
        ws.close()
      }
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active])

  // Докинуть новые токены в уже открытый сокет (не трогая исходный эффект).
  useEffect(() => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    const toAdd = tokens.filter((t) => !watchedRef.current.has(t))
    if (toAdd.length === 0) return
    toAdd.forEach((t) => watchedRef.current.add(t))
    ws.send(JSON.stringify({ watch: toAdd }))
  }, [tokens])

  return statuses
}
