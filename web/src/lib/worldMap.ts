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

// UN M49 numeric code for Antarctica -- not a G20 sovereign, never covered,
// and excluded entirely rather than just left unhighlighted (see below).
const ANTARCTICA_NUMERIC_ID = '010'

let cached: FeatureCollection<Geometry> | null = null

/** Build a GeoJSON FeatureCollection where each feature's `iso3` property is
 * our ISO3 code for the 19 covered countries, and `undefined` for every
 * other country (rendered as unhighlighted base geography, never matched).
 * Antarctica is dropped from the collection entirely.
 *
 * Built via `topojson-client`'s `feature()`, which converts each country's
 * topology arcs to a Polygon/MultiPolygon in raw (unprojected) longitude/
 * latitude space -- it does not itself introduce antimeridian artifacts.
 * Those came from the *previous* renderer (ECharts' `map` series, which
 * uses a plain equirectangular projection with no antimeridian-aware
 * clipping): Russia's Natural Earth geometry is split across +/-180
 * longitude, and without sphere-aware clipping, straight-line rendering of
 * those arcs draws a long horizontal streak connecting the two halves. A
 * `d3.geoPath` renderer (see RiskMap.tsx) clips every projection against
 * the sphere before rasterizing to SVG path data, so the same geometry
 * renders correctly there -- fixing the renderer, not the data.
 *
 * Antarctica is a separate, unrelated artifact with the same visual
 * symptom (a long horizontal band): its 110m geometry spans the full
 * longitude range at extreme southern latitude, which most projections
 * render as a wide band hugging the bottom of the map rather than a
 * recognisable landmass. It carries zero analytical relevance for a G20
 * sovereign-risk map, so it's dropped outright instead of being clipped or
 * specially projected.
 */
export function buildWorldGeoJson(): FeatureCollection<Geometry> {
  if (cached) return cached
  const topology = worldTopology as unknown as Topology
  const collection = feature(
    topology,
    topology.objects.countries as GeometryCollection,
  ) as unknown as FeatureCollection<Geometry>
  collection.features = collection.features.filter((f) => String(f.id) !== ANTARCTICA_NUMERIC_ID)
  for (const f of collection.features) {
    const id = String(f.id)
    f.properties = { ...f.properties, iso3: NUMERIC_TO_ISO3[id] }
  }
  cached = collection
  return collection
}
