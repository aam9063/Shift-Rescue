import { useState, type FormEvent } from 'react'
import { login } from '../services/auth'
import { ApiError, NetworkError } from '../services/apiClient'
import { Button } from '../components/ui/Button'

/**
 * Login screen for the manager dashboard (spec §7.5). Single email/password
 * form styled with the existing design tokens; shows the demo credentials for
 * reviewers and distinct messages for wrong credentials vs. an unreachable
 * server. Credentials are never logged.
 */

const DEMO_EMAIL = 'manager@laterraza.demo'
const DEMO_PASSWORD = 'laterraza-demo-2026'

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return 'Invalid email or password.'
  }
  if (error instanceof NetworkError) {
    return 'Cannot reach the server. Check your connection and try again.'
  }
  return 'Something went wrong. Please try again.'
}

const inputClasses =
  'mt-1 w-full rounded-card border border-input-border bg-white px-3 py-2 text-base text-text-primary'

export function LoginScreen({ onLogin }: { onLogin?: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    login(email, password)
      .then(() => onLogin?.())
      .catch((loginError: unknown) => setError(errorMessage(loginError)))
      .finally(() => setSubmitting(false))
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4 font-sans">
      <div className="w-full max-w-sm space-y-6 rounded-card bg-surface p-8 shadow-card">
        <div className="space-y-1">
          <p className="text-sm font-semibold uppercase tracking-wide text-green-accent">
            Shift Rescue
          </p>
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-green-starbucks">
            Manager sign in
          </h1>
          <p className="text-sm tracking-tight text-text-secondary">
            Sign in to see today&apos;s shifts, rescues and approvals.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" aria-label="Sign in">
          <label className="block text-sm tracking-tight text-text-secondary">
            Email
            <input
              type="email"
              name="email"
              autoComplete="email"
              required
              value={email}
              onChange={(changeEvent) => setEmail(changeEvent.target.value)}
              className={inputClasses}
            />
          </label>
          <label className="block text-sm tracking-tight text-text-secondary">
            Password
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(changeEvent) => setPassword(changeEvent.target.value)}
              className={inputClasses}
            />
          </label>

          {error && (
            <p role="alert" className="text-sm font-medium tracking-tight text-error">
              {error}
            </p>
          )}

          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

        <div className="rounded-card bg-gold-lightest px-4 py-3 text-sm tracking-tight text-text-primary">
          <p className="font-semibold">Demo credentials</p>
          <p className="text-text-secondary">
            {DEMO_EMAIL} · password {DEMO_PASSWORD}
          </p>
        </div>
      </div>
    </div>
  )
}
