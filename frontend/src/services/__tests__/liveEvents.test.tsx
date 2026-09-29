/**
 * Live channel contract (spec §7.5, §7.6).
 *
 * jsdom has no WebSocket, so these tests install a fake one: the contract worth
 * pinning is the URL (with the session token), which query keys each event
 * invalidates, the backoff on a lost connection, the session clearing on 4401
 * and the cleanup on unmount — not the transport.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import { useLiveEvents, queryKeysForEvent, socketUrl } from '../liveEvents'
import { clearSession, setSession } from '../auth'

// The hook resolves the location through the API before it opens the socket;
// the transport is not what these tests are about.
vi.mock('../api', () => ({
  getLocationId: vi.fn(async () => 'loc_1'),
}))

class FakeSocket {
  static instances: FakeSocket[] = []
  url: string
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  closed = false

  constructor(url: string) {
    this.url = url
    FakeSocket.instances.push(this)
  }

  close() {
    this.closed = true
  }

  emitOpen() {
    this.onopen?.()
  }

  emitEvent(name: string) {
    this.onmessage?.({ data: JSON.stringify({ name, location_id: 'loc' }) })
  }

  emitClose(code = 1006) {
    this.closed = true
    this.onclose?.({ code })
  }
}

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

function session() {
  setSession({
    accessToken: 'test-token',
    manager: { id: 'mgr_1', name: 'Demo Manager', email: 'm@x.demo', role: 'manager', locationIds: ['loc_1'] },
  })
}

beforeEach(() => {
  FakeSocket.instances = []
  vi.stubGlobal('WebSocket', FakeSocket as unknown as typeof WebSocket)
  // The suite runs with VITE_USE_MOCK=true (offline dashboard): the live channel
  // is deliberately inert there, so these cases opt out of mock mode.
  vi.stubEnv('VITE_USE_MOCK', 'false')
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  clearSession()
})

describe('socketUrl', () => {
  it('carries the location and the token', () => {
    expect(socketUrl('loc_1', 'tok')).toBe(
      `${location.origin.replace('http', 'ws')}/ws/locations/loc_1?token=tok`,
    )
  })
})

describe('queryKeysForEvent', () => {
  it('maps each event family to the keys the screens refetch', () => {
    expect(queryKeysForEvent('CASE_ESCALATED')).toContainEqual(['rescues'])
    expect(queryKeysForEvent('OFFER_ACCEPTED')).toContainEqual(['shifts'])
    expect(queryKeysForEvent('MESSAGE_RECEIVED')).toContainEqual(['demo-thread'])
    expect(queryKeysForEvent('APPROVAL_DECIDED')).toContainEqual(['approvals'])
  })

  it('an unknown event invalidates nothing', () => {
    expect(queryKeysForEvent('SOMETHING_ELSE')).toEqual([])
  })
})

describe('useLiveEvents', () => {
  it('opens the authenticated socket and invalidates on an event', async () => {
    session()
    const client = new QueryClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')

    const { result } = renderHook(() => useLiveEvents(), { wrapper: wrapper(client) })

    await waitFor(() => expect(FakeSocket.instances.length).toBe(1))
    expect(FakeSocket.instances[0].url).toContain('/ws/locations/loc_1?token=test-token')

    FakeSocket.instances[0].emitOpen()
    await waitFor(() => expect(result.current).toBe('live'))

    FakeSocket.instances[0].emitEvent('OFFER_ACCEPTED')
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['rescues'] }),
    )
  })

  it('clears the session when the server closes with 4401', async () => {
    session()
    const client = new QueryClient()
    renderHook(() => useLiveEvents(), { wrapper: wrapper(client) })

    await waitFor(() => expect(FakeSocket.instances.length).toBe(1))
    FakeSocket.instances[0].emitClose(4401)

    await waitFor(() => expect(localStorage.getItem('shift-rescue.session')).toBeNull())
  })

  it('reconnects with backoff after a lost connection', async () => {
    vi.useFakeTimers()
    session()
    const client = new QueryClient()
    renderHook(() => useLiveEvents(), { wrapper: wrapper(client) })

    await vi.waitFor(() => expect(FakeSocket.instances.length).toBe(1))
    FakeSocket.instances[0].emitClose(1006)

    await vi.advanceTimersByTimeAsync(1100)
    await vi.waitFor(() => expect(FakeSocket.instances.length).toBe(2))
  })

  it('closes the socket on unmount without reconnecting', async () => {
    session()
    const client = new QueryClient()
    const { unmount } = renderHook(() => useLiveEvents(), { wrapper: wrapper(client) })

    await waitFor(() => expect(FakeSocket.instances.length).toBe(1))
    const socket = FakeSocket.instances[0]
    unmount()

    expect(socket.closed).toBe(true)
  })

  it('stays offline without a session', async () => {
    const client = new QueryClient()
    const { result } = renderHook(() => useLiveEvents(), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current).toBe('offline'))
    expect(FakeSocket.instances).toHaveLength(0)
  })
})
