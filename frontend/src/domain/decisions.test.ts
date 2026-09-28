import { describe, expect, it } from 'vitest'
import { decisionTime } from './decisions'

describe('decisionTime', () => {
  it('turns the API timestamp into a compact local time', () => {
    // 19:27 UTC renders as 21:27 in Europe/Madrid; assert the shape, not the
    // zone, so the test is not tied to the runner's timezone.
    expect(decisionTime('2026-09-25T19:27:33.483410+00:00')).toMatch(/^\d{2}:\d{2}$/)
  })

  it('keeps an already compact time as it is (the mock fixture shape)', () => {
    expect(decisionTime('15:03')).toBe('15:03')
  })

  it('shows an unparseable value instead of hiding it', () => {
    expect(decisionTime('not-a-time')).toBe('not-a-time')
  })
})
