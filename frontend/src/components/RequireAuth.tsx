import { useEffect, useState, type ReactNode } from 'react'
import { clearSession, isAuthenticated, SESSION_EXPIRED_EVENT } from '../services/auth'
import { LoginScreen } from '../screens/LoginScreen'

/**
 * Guard for the dashboard routes: an unauthenticated visitor lands on the
 * login screen, and any 401 from an API call (session expired or revoked)
 * bounces the user back to login. After signing in the user continues to the
 * view they asked for (the app shell restores the route from the URL hash).
 * The signed-in shell receives `signOut` — the single way to end a session:
 * clear storage and return to the login screen. Children may also be a plain
 * node (no sign-out access) for simple guards.
 */
export function RequireAuth({
  children,
}: {
  children: ReactNode | ((signOut: () => void) => ReactNode)
}) {
  const [authenticated, setAuthenticated] = useState(isAuthenticated)

  useEffect(() => {
    const handleSessionExpired = () => setAuthenticated(false)
    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired)
  }, [])

  if (!authenticated) {
    return <LoginScreen onLogin={() => setAuthenticated(true)} />
  }
  const signOut = () => {
    clearSession()
    setAuthenticated(false)
  }
  if (typeof children === 'function') {
    return <>{children(signOut)}</>
  }
  return <>{children}</>
}
