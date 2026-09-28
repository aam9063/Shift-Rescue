import { apiFetch } from './apiClient'

/**
 * Token-based session for the manager dashboard (spec §7.5). The whole
 * session (token + manager profile) is stored in `localStorage` under one
 * key. No password or token is ever logged.
 */

/** Dispatched on `window` whenever any API call answers 401. */
export const SESSION_EXPIRED_EVENT = 'shift-rescue:session-expired'

export interface ManagerProfile {
  id: string
  name: string
  email: string
  role: string
  locationIds: string[]
}

export interface AuthSession {
  accessToken: string
  manager: ManagerProfile
}

const STORAGE_KEY = 'shift-rescue.session'

export function getSession(): AuthSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as AuthSession
    return typeof parsed.accessToken === 'string' ? parsed : null
  } catch {
    return null
  }
}

export function getToken(): string | null {
  return getSession()?.accessToken ?? null
}

export function setSession(session: AuthSession): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
}

export function clearSession(): void {
  localStorage.removeItem(STORAGE_KEY)
}

export function isAuthenticated(): boolean {
  return getToken() !== null
}

interface LoginResponse {
  accessToken: string
  manager: ManagerProfile
}

/**
 * `POST /api/auth/login` and store the returned token plus the manager
 * profile. Invalid credentials reject with `ApiError` (401) from the client.
 */
export async function login(email: string, password: string): Promise<AuthSession> {
  const data = await apiFetch<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  const session: AuthSession = { accessToken: data.accessToken, manager: data.manager }
  setSession(session)
  return session
}
