/**
 * Live dashboard channel (spec §7.5 `WS /ws/locations/{id}`, §7.6).
 *
 * The screens keep rendering from the API; this channel only tells them what to
 * refetch. One event type maps to the same query keys the actions already
 * invalidate, so nothing is duplicated in the client cache.
 *
 * It degrades exactly like the rest of the dashboard: a socket that cannot open,
 * a broker that is down or a token that expired never breaks a screen. A 4401
 * means the session is gone, which is handled the same way the HTTP client
 * handles it (clear the session and let the guard show the login).
 */

import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { getLocationId } from './api'
import { clearSession, getToken } from './auth'
import { isMockMode } from './dataSource'

export type LiveState = 'connecting' | 'live' | 'offline'

/** Close codes the API uses (see `app/api/ws.py`). */
const CLOSE_UNAUTHORIZED = 4401
const RECONNECT_MIN_MS = 1000
const RECONNECT_MAX_MS = 15000

/** Query prefix keys each event implies, mirroring the action invalidations. */
const RESCUE_KEYS = [
  ['rescues'],
  ['shifts'],
  ['approvals'],
  ['conversations'],
  ['demo-employees'],
]
const MESSAGE_KEYS = [['conversations'], ['demo-thread'], ['metrics'], ['agent-decisions']]
const APPROVAL_KEYS = [['approvals'], ['rescues'], ['shifts']]

const EVENT_KEYS: Record<string, string[][]> = {
  RESCUE_OPENED: RESCUE_KEYS,
  OFFERS_SENT: RESCUE_KEYS,
  OFFER_ACCEPTED: RESCUE_KEYS,
  OFFER_DECLINED: RESCUE_KEYS,
  CASE_COVERED: RESCUE_KEYS,
  CASE_ESCALATED: RESCUE_KEYS,
  CASE_CLOSED: RESCUE_KEYS,
  MESSAGE_RECEIVED: MESSAGE_KEYS,
  MESSAGE_SENT: MESSAGE_KEYS,
  APPROVAL_REQUESTED: APPROVAL_KEYS,
  APPROVAL_DECIDED: APPROVAL_KEYS,
}

/** The query keys an event name invalidates; unknown events invalidate nothing. */
export function queryKeysForEvent(name: string): string[][] {
  return EVENT_KEYS[name] ?? []
}

/** `ws(s)://host` for the same origin, or the configured override. */
export function socketBaseUrl(): string {
  const configured = import.meta.env.VITE_WS_BASE_URL
  if (configured) {
    return configured.replace(/\/$/, '')
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

/** The socket URL for a location and token (exported for the tests). */
export function socketUrl(locationId: string, token: string): string {
  return `${socketBaseUrl()}/ws/locations/${encodeURIComponent(locationId)}?token=${encodeURIComponent(token)}`
}

export function useLiveEvents(enabled = true): LiveState {
  const queryClient = useQueryClient()
  const [state, setState] = useState<LiveState>('offline')
  const retries = useRef(0)

  useEffect(() => {
    if (!enabled || isMockMode()) {
      // Mock mode is the offline dashboard: the channel stays inert. The state
      // already starts as 'offline', so nothing is set synchronously here.
      return
    }
    let socket: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let closed = false

    const connect = async () => {
      const token = getToken()
      if (closed) return
      if (!token) {
        setState('offline')
        return
      }
      let locationId: string
      try {
        locationId = await getLocationId()
      } catch {
        // The dashboard will surface the API failure; the channel just waits.
        setState('offline')
        return
      }
      if (closed) return

      setState('connecting')
      try {
        socket = new WebSocket(socketUrl(locationId, token))
      } catch {
        scheduleReconnect()
        return
      }

      socket.onopen = () => {
        retries.current = 0
        setState('live')
      }
      socket.onmessage = (message) => {
        let name: string | undefined
        try {
          name = (JSON.parse(String(message.data)) as { name?: string }).name
        } catch {
          return // a frame the API never sends: ignore it, never crash
        }
        if (!name) return
        for (const queryKey of queryKeysForEvent(name)) {
          void queryClient.invalidateQueries({ queryKey })
        }
      }
      socket.onclose = (event) => {
        socket = null
        setState('offline')
        if (event.code === CLOSE_UNAUTHORIZED) {
          // The session is gone: same handling as the HTTP 401 path.
          clearSession()
          return
        }
        scheduleReconnect()
      }
      socket.onerror = () => {
        // onclose follows and owns the reconnect.
      }
    }

    const scheduleReconnect = () => {
      if (closed) return
      const delay = Math.min(RECONNECT_MIN_MS * 2 ** retries.current, RECONNECT_MAX_MS)
      retries.current += 1
      timer = setTimeout(() => void connect(), delay)
    }

    void connect()

    return () => {
      closed = true
      if (timer !== undefined) clearTimeout(timer)
      if (socket !== null) {
        // Detach the handlers: unmount is not a connection failure.
        socket.onclose = null
        socket.onmessage = null
        socket.onopen = null
        socket.onerror = null
        socket.close()
      }
    }
  }, [enabled, queryClient])

  return state
}
