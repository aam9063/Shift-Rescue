/**
 * Presentation helpers for the Agent decisions screen (spec §7.6 screen 8).
 */

/**
 * The API returns ISO-8601 (`2026-09-25T19:27:33.483410+00:00`) while the mock
 * fixtures carried an already formatted `15:03`. Rendering the API field
 * verbatim put an unreadable timestamp in the table, so the screen formats it
 * into a compact local time. A value that is already compact passes through,
 * and an unparseable one is shown as it came rather than swallowed.
 */
export function decisionTime(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}
