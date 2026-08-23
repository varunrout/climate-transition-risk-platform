import { useQuery } from '@tanstack/react-query'
import {
  fetchBacktestMetrics,
  fetchCountries,
  fetchCountryOverview,
  fetchCountryTimeseries,
  fetchEnergyIndicators,
  fetchManifest,
  fetchRegimeDiagnostics,
  fetchRiskComponents,
  fetchRunMetadata,
  fetchScenarioQuantiles,
} from './dataClient'

/**
 * One query hook per bundle file. `staleTime: Infinity` is deliberate: this
 * is a static, versioned snapshot (see the manifest hash) rather than
 * live data, so there is nothing to revalidate against within a session.
 */
const STATIC_OPTIONS = { staleTime: Number.POSITIVE_INFINITY, retry: 1 } as const

export function useManifest() {
  return useQuery({ queryKey: ['manifest'], queryFn: fetchManifest, ...STATIC_OPTIONS })
}

export function useCountries() {
  return useQuery({ queryKey: ['countries'], queryFn: fetchCountries, ...STATIC_OPTIONS })
}

export function useCountryOverview() {
  return useQuery({
    queryKey: ['country-overview'],
    queryFn: fetchCountryOverview,
    ...STATIC_OPTIONS,
  })
}

export function useCountryTimeseries() {
  return useQuery({
    queryKey: ['country-timeseries'],
    queryFn: fetchCountryTimeseries,
    ...STATIC_OPTIONS,
  })
}

export function useRiskComponents() {
  return useQuery({
    queryKey: ['risk-components'],
    queryFn: fetchRiskComponents,
    ...STATIC_OPTIONS,
  })
}

export function useScenarioQuantiles() {
  return useQuery({
    queryKey: ['scenario-quantiles'],
    queryFn: fetchScenarioQuantiles,
    ...STATIC_OPTIONS,
  })
}

export function useBacktestMetrics() {
  return useQuery({
    queryKey: ['backtest-metrics'],
    queryFn: fetchBacktestMetrics,
    ...STATIC_OPTIONS,
  })
}

export function useEnergyIndicators() {
  return useQuery({
    queryKey: ['energy-indicators'],
    queryFn: fetchEnergyIndicators,
    ...STATIC_OPTIONS,
  })
}

export function useRegimeDiagnostics() {
  return useQuery({
    queryKey: ['regime-diagnostics'],
    queryFn: fetchRegimeDiagnostics,
    ...STATIC_OPTIONS,
  })
}

export function useRunMetadata() {
  return useQuery({ queryKey: ['run-metadata'], queryFn: fetchRunMetadata, ...STATIC_OPTIONS })
}
