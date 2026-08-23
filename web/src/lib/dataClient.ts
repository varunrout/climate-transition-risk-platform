import {
  BacktestMetricSchema,
  CountryIndexEntrySchema,
  CountryOverviewSchema,
  CountryTimeseriesSchema,
  EnergyIndicatorSchema,
  RegimeDiagnosticSchema,
  RiskComponentSchema,
  RunMetadataSchema,
  ScenarioQuantileSchema,
  SUPPORTED_SCHEMA_VERSIONS,
  WebManifestSchema,
  type BacktestMetric,
  type CountryIndexEntry,
  type CountryOverview,
  type CountryTimeseries,
  type EnergyIndicator,
  type RegimeDiagnostic,
  type RiskComponent,
  type RunMetadata,
  type ScenarioQuantile,
  type WebManifest,
} from './schemas'
import { z } from 'zod'

/** Raised when the bundle is missing, malformed, or an incompatible schema version. */
export class BundleError extends Error {
  readonly kind: 'missing' | 'invalid_json' | 'schema_mismatch' | 'schema_invalid'

  constructor(kind: BundleError['kind'], message: string) {
    super(message)
    this.name = 'BundleError'
    this.kind = kind
  }
}

const DATA_BASE_URL = `${import.meta.env.BASE_URL}data/`.replace(/\/\/data\//, '/data/')

async function fetchJson(fileName: string): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(`${DATA_BASE_URL}${fileName}`)
  } catch {
    throw new BundleError('missing', `Could not reach data bundle file "${fileName}".`)
  }
  if (!response.ok) {
    throw new BundleError(
      'missing',
      `Data bundle file "${fileName}" returned HTTP ${response.status}.`,
    )
  }
  try {
    return await response.json()
  } catch {
    throw new BundleError('invalid_json', `Data bundle file "${fileName}" is not valid JSON.`)
  }
}

async function fetchAndValidate<T>(fileName: string, schema: z.ZodType<T>): Promise<T> {
  const raw = await fetchJson(fileName)
  const result = schema.safeParse(raw)
  if (!result.success) {
    throw new BundleError(
      'schema_invalid',
      `Data bundle file "${fileName}" does not match the expected contract: ${result.error.message}`,
    )
  }
  return result.data
}

export async function fetchManifest(): Promise<WebManifest> {
  const manifest = await fetchAndValidate('manifest.json', WebManifestSchema)
  if (!SUPPORTED_SCHEMA_VERSIONS.includes(manifest.schema_version)) {
    throw new BundleError(
      'schema_mismatch',
      `This dashboard build supports web bundle schema version(s) ${SUPPORTED_SCHEMA_VERSIONS.join(', ')}, ` +
        `but the loaded bundle is "${manifest.schema_version}". Refusing to render potentially ` +
        `incorrect fields -- rebuild the frontend or regenerate the bundle so versions match.`,
    )
  }
  return manifest
}

export async function fetchCountries(): Promise<CountryIndexEntry[]> {
  return fetchAndValidate('countries.json', z.array(CountryIndexEntrySchema))
}

export async function fetchCountryOverview(): Promise<CountryOverview[]> {
  return fetchAndValidate('country-overview.json', z.array(CountryOverviewSchema))
}

export async function fetchCountryTimeseries(): Promise<CountryTimeseries[]> {
  return fetchAndValidate('country-timeseries.json', z.array(CountryTimeseriesSchema))
}

export async function fetchRiskComponents(): Promise<RiskComponent[]> {
  return fetchAndValidate('risk-components.json', z.array(RiskComponentSchema))
}

export async function fetchScenarioQuantiles(): Promise<ScenarioQuantile[]> {
  return fetchAndValidate('scenario-quantiles.json', z.array(ScenarioQuantileSchema))
}

export async function fetchBacktestMetrics(): Promise<BacktestMetric[]> {
  return fetchAndValidate('backtest-metrics.json', z.array(BacktestMetricSchema))
}

export async function fetchEnergyIndicators(): Promise<EnergyIndicator[]> {
  return fetchAndValidate('energy-indicators.json', z.array(EnergyIndicatorSchema))
}

export async function fetchRegimeDiagnostics(): Promise<RegimeDiagnostic[]> {
  return fetchAndValidate('regime-diagnostics.json', z.array(RegimeDiagnosticSchema))
}

export async function fetchRunMetadata(): Promise<RunMetadata> {
  const rows = await fetchAndValidate('run-metadata.json', z.array(RunMetadataSchema))
  if (rows.length === 0) {
    throw new BundleError('schema_invalid', 'run-metadata.json contained no rows.')
  }
  return rows[0]
}
