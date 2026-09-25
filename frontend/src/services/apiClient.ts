import { clearSession, getToken, SESSION_EXPIRED_EVENT } from './auth'

/**
 * Thin HTTP client for the Shift Rescue API. Every dashboard request goes
 * through here so auth headers, error mapping and 401 handling live in one
 * place. No token or password is ever logged.
 */

/** Non-2xx response carrying the HTTP status and a safe, non-secret message. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** The server could not be reached at all — the UI shows this as offline. */
export class NetworkError extends Error {
  constructor(cause?: unknown) {
    super('Cannot reach the server')
    this.name = 'NetworkError'
    this.cause = cause
  }
}

/**
 * Base URL from the environment. Empty (the default) means same-origin:
 * the Vite dev proxy and the deployed Caddy setup both serve `/api`.
 */
export function apiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  return raw ? raw.replace(/\/+$/, '') : ''
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  return headers
}

/** Extract a displayable message without echoing credentials or tokens. */
async function safeErrorMessage(response: Response): Promise<string> {
  const fallback = `Request failed with status ${response.status}`
  try {
    const body: unknown = await response.json()
    if (body !== null && typeof body === 'object') {
      const detail = (body as { detail?: unknown }).detail
      if (typeof detail === 'string' && detail.length > 0) {
        return detail
      }
    }
  } catch {
    // Non-JSON error body: fall back to the generic message.
  }
  return fallback
}

/**
 * Perform a JSON API request. Resolves with the parsed body; rejects with
 * `ApiError` (status + safe message) for non-2xx responses and `NetworkError`
 * when the request never reaches the server. A 401 always clears the session
 * and notifies the app so the user is sent back to the login screen.
 */
export async function apiFetch<T>(path: string, init: Omit<RequestInit, 'headers'> = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, { ...init, headers: authHeaders() })
  } catch (error) {
    throw new NetworkError(error)
  }

  if (!response.ok) {
    if (response.status === 401) {
      // Never swallow a 401: the session is dead wherever this happens.
      clearSession()
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
    }
    throw new ApiError(response.status, await safeErrorMessage(response))
  }

  const text = await response.text()
  try {
    return JSON.parse(text) as T
  } catch {
    throw new ApiError(response.status, 'Unexpected response from the server')
  }
}
