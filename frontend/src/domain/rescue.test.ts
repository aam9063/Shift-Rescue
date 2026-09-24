import { describe, expect, it } from 'vitest'
import type { AuditEvent, CandidateResult } from './types'
import { eventLabel, sortEventsChronologically, orderCandidates } from './rescue'

function event(overrides: Partial<AuditEvent> & { id: string; type: AuditEvent['type'] }): AuditEvent {
  return {
    rescueId: 'rescue_001',
    actor: 'system',
    createdAt: '2026-10-03T06:40:00+02:00',
    ...overrides,
  }
}

describe('sortEventsChronologically', () => {
  it('orders events from oldest to newest', () => {
    const events = [
      event({ id: 'e2', type: 'OFFER_SENT', createdAt: '2026-10-03T06:42:00+02:00' }),
      event({ id: 'e1', type: 'RESCUE_OPENED', createdAt: '2026-10-03T06:40:00+02:00' }),
    ]
    expect(sortEventsChronologically(events).map((e) => e.id)).toEqual(['e1', 'e2'])
  })

  it('breaks ties deterministically by event id', () => {
    const events = [
      event({ id: 'b', type: 'OFFER_SENT', createdAt: '2026-10-03T06:42:00+02:00' }),
      event({ id: 'a', type: 'OFFER_SENT', createdAt: '2026-10-03T06:42:00+02:00' }),
    ]
    expect(sortEventsChronologically(events).map((e) => e.id)).toEqual(['a', 'b'])
  })
})

describe('eventLabel', () => {
  it('maps event types to human-readable English labels', () => {
    expect(eventLabel('RESCUE_OPENED')).toBe('Rescue opened')
    expect(eventLabel('OFFER_SENT')).toBe('Offer sent')
    expect(eventLabel('OFFER_DECLINED')).toBe('Offer declined')
    expect(eventLabel('OFFER_ACCEPTED')).toBe('Offer accepted')
    expect(eventLabel('SHIFT_ASSIGNED')).toBe('Shift assigned in HRIS')
    expect(eventLabel('ESCALATED')).toBe('Escalated to manager')
  })

  it('never exposes raw internal type names to the UI', () => {
    for (const type of ['RESCUE_OPENED', 'OFFER_SENT', 'OFFER_ACCEPTED'] as const) {
      expect(eventLabel(type)).not.toBe(type)
    }
  })
})

describe('orderCandidates', () => {
  const candidates: CandidateResult[] = [
    { employeeId: 'emp_1', name: 'Ana', score: 0.82, eligible: true, requiresApproval: false, reasons: [] },
    { employeeId: 'emp_3', name: 'Caro', score: 0.95, eligible: false, requiresApproval: false, reasons: [{ code: 'REST_VIOLATION', message: 'Only 7.5h rest' }] },
    { employeeId: 'emp_2', name: 'Bruno', score: 0.82, eligible: true, requiresApproval: true, reasons: [] },
  ]

  it('orders by score descending with deterministic id tie-break', () => {
    expect(orderCandidates(candidates).map((c) => c.employeeId)).toEqual(['emp_3', 'emp_1', 'emp_2'])
  })

  it('does not mutate the input array', () => {
    const copy = [...candidates]
    orderCandidates(candidates)
    expect(candidates).toEqual(copy)
  })
})
