import { feature } from 'topojson-client'
import type { Topology, GeometryCollection } from 'topojson-specification'
import type { FeatureCollection, Geometry } from 'geojson'
// world-atlas ships Natural Earth (public domain) 110m topology -- no API
// key, no attribution requirement, safe for a static portfolio site.
import worldTopology from 'world-atlas/countries-110m.json'

/** UN M49 numeric country code -> our ISO3 code, for the 19 G20 sovereigns this platform covers. */
export const NUMERIC_TO_ISO3: Record<string, string> = {
  '032': 'ARG',
  '036': 'AUS',
  '076': 'BRA',
  '124': 'CAN',
  '156': 'CHN',
  '276': 'DEU',
  '250': 'FRA',
  '826': 'GBR',
  '360': 'IDN',
  '356': 'IND',
  '380': 'ITA',
  '392': 'JPN',
  '410': 'KOR',
  '484': 'MEX',
  '643': 'RUS',
  '682': 'SAU',
  '792': 'TUR',
  '840': 'USA',
  '710': 'ZAF',
}

let cached: FeatureCollection<Geometry> | null = null

/** Build a GeoJSON FeatureCollection where each feature's `name` is our ISO3
 * code for the 19 covered countries (so ECharts map series can match on
 * `name`), leaving every other country's name as its numeric id (never
 * matched, rendered as unhighlighted base geography). */
export function buildWorldGeoJson(): FeatureCollection<Geometry> {
  if (cached) return cached
  const topology = worldTopology as unknown as Topology
  const collection = feature(
    topology,
    topology.objects.countries as GeometryCollection,
  ) as unknown as FeatureCollection<Geometry>
  for (const f of collection.features) {
    const id = String(f.id)
    f.properties = { ...f.properties, name: NUMERIC_TO_ISO3[id] ?? id }
  }
  cached = collection
  return collection
}
