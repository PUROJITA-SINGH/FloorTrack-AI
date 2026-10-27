import type { KeyboardEvent } from 'react'

export type FloorMapZone = {
  id: string
  name: string
  polygon_json: readonly (readonly [number, number])[] | string
}

export type FloorMapAsset = {
  id: string
  current_zone_id: string | null
  confidence_band: 'high' | 'medium' | 'low' | 'stale' | string
  decision_status: string
  code: string
  zone?: string | null
  freshness?: number | null
  operational_status?: string | null
  status_source?: string | null
}

type FloorMapProps = {
  zones: FloorMapZone[]
  assets: FloorMapAsset[]
  onSelectAsset: (asset: FloorMapAsset) => void
  highlightedAssetIds?: readonly string[]
}

type Point = readonly [number, number]

const bandColors: Record<string, string> = {
  high: 'var(--band-high)',
  medium: 'var(--band-med)',
  low: 'var(--band-low)',
  stale: 'var(--text-3)',
}

function getPolygon(value: FloorMapZone['polygon_json']): Point[] {
  let parsed: unknown = value
  if (typeof value === 'string') {
    try {
      parsed = JSON.parse(value)
    } catch {
      return []
    }
  }

  if (!Array.isArray(parsed)) return []
  return parsed.filter(
    (point): point is Point =>
      Array.isArray(point) &&
      point.length >= 2 &&
      typeof point[0] === 'number' &&
      Number.isFinite(point[0]) &&
      typeof point[1] === 'number' &&
      Number.isFinite(point[1]),
  )
}

function getCentroid(points: Point[]): Point | null {
  if (points.length < 3) return null

  let twiceArea = 0
  let xSum = 0
  let ySum = 0
  for (let index = 0; index < points.length; index += 1) {
    const [x, y] = points[index]
    const [nextX, nextY] = points[(index + 1) % points.length]
    const cross = x * nextY - nextX * y
    twiceArea += cross
    xSum += (x + nextX) * cross
    ySum += (y + nextY) * cross
  }

  if (twiceArea === 0) return null
  return [xSum / (3 * twiceArea), ySum / (3 * twiceArea)]
}

function FloorMap({
  zones,
  assets,
  onSelectAsset,
  highlightedAssetIds = [],
}: FloorMapProps) {
  const mappedZones = zones
    .map((zone) => {
      const points = getPolygon(zone.polygon_json)
      return { zone, points, centroid: getCentroid(points) }
    })
    .filter(
      (
        entry,
      ): entry is {
        zone: FloorMapZone
        points: Point[]
        centroid: Point
      } => entry.centroid !== null,
    )

  const zoneById = new Map(mappedZones.map(({ zone, centroid }) => [zone.id, centroid]))
  const assetsByZone = new Map<string, FloorMapAsset[]>()
  for (const asset of assets) {
    if (!asset.current_zone_id) continue
    const siblings = assetsByZone.get(asset.current_zone_id) ?? []
    siblings.push(asset)
    assetsByZone.set(asset.current_zone_id, siblings)
  }

  return (
    <svg
      viewBox="0 0 100 100"
      role="group"
      aria-label="Floor map"
      preserveAspectRatio="xMidYMid meet"
      style={{
        display: 'block',
        width: '100%',
        height: '100%',
        background: 'var(--surface-0)',
      }}
    >
      {mappedZones.map(({ zone, points }) => {
        // Zone names sit in the top-left corner of each zone so that the asset
        // markers, which cluster around the zone centre, never cover them.
        const labelX = Math.min(...points.map(([x]) => x)) + 1.5
        const labelY = Math.min(...points.map(([, y]) => y)) + 3
        return (
          <g key={zone.id}>
            <polygon
              points={points.map(([x, y]) => `${x},${y}`).join(' ')}
              fill="var(--surface-2)"
              stroke="var(--border)"
              strokeWidth="0.5"
            />
            <text
              x={labelX}
              y={labelY}
              fill="var(--text-2)"
              fontSize="2.2"
              fontWeight="600"
              textAnchor="start"
              dominantBaseline="middle"
              style={{ pointerEvents: 'none', userSelect: 'none' }}
              aria-hidden="true"
            >
              {zone.name}
            </text>
          </g>
        )
      })}

      {assets.map((asset) => {
        const zoneId = asset.current_zone_id
        if (!zoneId) return null
        const centroid = zoneById.get(zoneId)
        if (!centroid) return null

        const siblings = assetsByZone.get(zoneId) ?? [asset]
        const siblingIndex = siblings.findIndex((sibling) => sibling.id === asset.id)
        const angle =
          siblings.length > 1
            ? (2 * Math.PI * siblingIndex) / siblings.length
            : Math.PI / 2
        const offset =
          siblings.length > 1
            ? Math.max(5.0, 3.5 / Math.sin(Math.PI / siblings.length))
            : 4.8
        const x = centroid[0] + Math.cos(angle) * offset
        const y = centroid[1] + Math.sin(angle) * offset
        const color = bandColors[asset.confidence_band] ?? 'var(--band-low)'
        const isStale = asset.confidence_band === 'stale'
        const isConflict = asset.decision_status === 'sensor_disagreement'
        const isHighlighted = highlightedAssetIds.includes(asset.id)
        const availability = asset.operational_status ?? 'status_unknown'
        const freshness =
          typeof asset.freshness === 'number'
            ? `${Math.round(asset.freshness)} seconds`
            : 'no estimate'
        const markerDescription = [
          asset.code,
          asset.zone ?? 'zone unknown',
          `${asset.confidence_band} confidence`,
          `freshness ${freshness}`,
          `availability ${availability}`,
          asset.status_source ? `source ${asset.status_source}` : 'source unknown',
        ].join(', ')

        const handleKeyDown = (event: KeyboardEvent<SVGGElement>) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            onSelectAsset(asset)
          }
        }

        return (
          <g
            key={asset.code}
            role="button"
            tabIndex={0}
            aria-label={markerDescription}
            onClick={() => onSelectAsset(asset)}
            onKeyDown={handleKeyDown}
            className={isHighlighted ? 'asset-marker-highlight' : undefined}
            style={{ cursor: 'pointer' }}
          >
            <title>{markerDescription}</title>
            {isConflict && (
              <>
                <circle
                  cx={x}
                  cy={y}
                  r="3.6"
                  fill="none"
                  stroke="var(--status-conflict)"
                  strokeWidth="0.5"
                  strokeDasharray="1 0.7"
                  vectorEffect="non-scaling-stroke"
                  aria-hidden="true"
                />
                <text
                  x={x + 3.8}
                  y={y - 2.5}
                  fill="var(--status-conflict)"
                  fontSize="1.5"
                  aria-hidden="true"
                >
                  ⚠
                </text>
              </>
            )}
            <circle
              cx={x}
              cy={y}
              r="2.5"
              fill={color}
              fillOpacity={isStale ? 0.5 : 1}
              stroke={color}
              strokeWidth="0.5"
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={x}
              y={y + 0.1}
              fill="#ffffff"
              fontSize="1.1"
              fontWeight="bold"
              textAnchor="middle"
              dominantBaseline="middle"
              aria-hidden="true"
              style={{ pointerEvents: 'none', userSelect: 'none' }}
            >
              {asset.code.replace(/^P-0*/, '')}
            </text>
            <text
              x={x}
              y={y + 3.8}
              fill="var(--text-1)"
              fontSize="1.2"
              fontWeight="600"
              textAnchor="middle"
              dominantBaseline="hanging"
              aria-hidden="true"
              style={{ pointerEvents: 'none', userSelect: 'none' }}
            >
              {asset.code}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export default FloorMap
