import type { DashboardDataSource } from './mock'
import { MockDashboardDataSource } from './mock'
import { ApiDashboardDataSource } from './api'

/**
 * Seam selection: the API data source is the default; the mock stays alive as
 * an explicit offline mode (offline demo and hermetic tests) via
 * `VITE_USE_MOCK=true`. Components never import a source directly — they go
 * through the hooks, which consume `dataSource` below.
 */

export function isMockMode(): boolean {
  return import.meta.env.VITE_USE_MOCK === 'true'
}

export function getDataSource(): DashboardDataSource {
  return isMockMode() ? new MockDashboardDataSource() : new ApiDashboardDataSource()
}

/** Single source instance for the app. */
export const dataSource: DashboardDataSource = getDataSource()
