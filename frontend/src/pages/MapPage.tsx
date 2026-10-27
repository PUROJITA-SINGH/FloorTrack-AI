import axios from 'axios'
import { useEffect, useRef, useState } from 'react'
import AssetSearch, { type SearchAsset } from '../components/AssetSearch'
import AssetDetailDrawer from '../components/AssetDetailDrawer'
import FloorMap, { type FloorMapAsset, type FloorMapZone } from '../components/FloorMap'

type MapAsset = FloorMapAsset & {
  asset_type_id: string
  asset_type_name: string | null
  operational_status: string | null
  status_source: string | null
  status_confirmed_at: string | null
  last_fusion_at: string | null
  zone?: string | null
  zone_id?: string | null
  freshness?: number | null
  updated_at?: string | null
  confidence_breakdown?: Record<string, number> | null
  camera_zone?: string | null
  camera_zone_name?: string | null
  ble_zone?: string | null
  ble_zone_name?: string | null
  gateway_count?: number | null
  decision_reason?: string | null
  disagreement_reason?: string | null
  status_stale_after?: string | null
  fusion_detail?: {
    camera_zone?: string | null
    ble_zone?: string | null
    gateway_count?: number | null
    ble_quality?: number | null
    reason?: string | null
    confidence_breakdown?: Record<string, number> | null
  }
}

type AssetApiResponse = Partial<MapAsset> & {
  id: string
  code: string
  asset_type?: string | null
}

function normalizeAsset(asset: AssetApiResponse): MapAsset {
  return {
    ...asset,
    id: asset.id,
    code: asset.code,
    current_zone_id: asset.current_zone_id ?? asset.zone_id ?? null,
    confidence_band: asset.confidence_band ?? 'stale',
    decision_status: asset.decision_status ?? 'unknown',
    asset_type_id: asset.asset_type_id ?? '',
    asset_type_name: asset.asset_type_name ?? asset.asset_type ?? null,
    operational_status: asset.operational_status ?? null,
    status_source: asset.status_source ?? null,
    status_confirmed_at: asset.status_confirmed_at ?? null,
    last_fusion_at: asset.last_fusion_at ?? null,
  }
}

function assetTimestamp(asset: MapAsset): string {
  return `${asset.updated_at ?? ''}|${asset.last_fusion_at ?? ''}`
}

const skeletonBarStyle = {
  display: 'block',
  width: '100%',
  height: 18,
  borderRadius: 6,
  background: 'linear-gradient(90deg, var(--surface-2) 25%, var(--border) 50%, var(--surface-2) 75%)',
  backgroundSize: '200% 100%',
  animation: 'pulse 1.2s ease-in-out infinite',
} as const

function MapPage() {
  const [zones, setZones] = useState<FloorMapZone[]>([])
  const [assets, setAssets] = useState<MapAsset[]>([])
  const [selectedAsset, setSelectedAsset] = useState<MapAsset | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [fusionRunning, setFusionRunning] = useState(false)
  const [fusionError, setFusionError] = useState<string | null>(null)
  const [highlightedAssetIds, setHighlightedAssetIds] = useState<string[]>([])
  const assetsRef = useRef<MapAsset[]>([])
  const pollingRef = useRef(false)
  const highlightTimeoutRef = useRef<number | null>(null)

  const syncAssets = (nextAssets: MapAsset[], requireTimestampChange: boolean) => {
    const previousAssets = assetsRef.current
    const previousById = new Map(previousAssets.map((asset) => [asset.id, asset]))
    const hasChanged =
      nextAssets.length !== previousAssets.length ||
      nextAssets.some((asset) => {
        const previous = previousById.get(asset.id)
        return !previous || assetTimestamp(previous) !== assetTimestamp(asset)
      })

    if (requireTimestampChange && !hasChanged) return false

    const changedMarkers = nextAssets
      .filter((asset) => {
        const previous = previousById.get(asset.id)
        return (
          previous !== undefined &&
          (previous.confidence_band !== asset.confidence_band ||
            previous.decision_status !== asset.decision_status)
        )
      })
      .map((asset) => asset.id)

    assetsRef.current = nextAssets
    setAssets(nextAssets)
    setSelectedAsset((current) => {
      if (!current) return current
      const refreshed = nextAssets.find((asset) => asset.id === current.id)
      return refreshed ? { ...current, ...refreshed } : current
    })

    if (changedMarkers.length > 0) {
      setHighlightedAssetIds(changedMarkers)
      if (highlightTimeoutRef.current !== null) {
        window.clearTimeout(highlightTimeoutRef.current)
      }
      highlightTimeoutRef.current = window.setTimeout(() => {
        setHighlightedAssetIds([])
        highlightTimeoutRef.current = null
      }, 500)
    }
    return hasChanged
  }

  const loadMapData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [zonesResponse, assetsResponse] = await Promise.all([
        axios.get<FloorMapZone[]>('/api/zones'),
        axios.get<AssetApiResponse[]>('/api/assets'),
      ])
      setZones(Array.isArray(zonesResponse.data) ? zonesResponse.data : [])
      const nextAssets = Array.isArray(assetsResponse.data)
        ? assetsResponse.data.map(normalizeAsset)
        : []
      syncAssets(nextAssets, false)
      setLastUpdated(new Date())
    } catch {
      setError('Could not load map data. Check connection and try again.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void Promise.resolve().then(loadMapData)
  }, [])

  useEffect(() => {
    const pollAssets = async () => {
      if (pollingRef.current) return
      pollingRef.current = true
      try {
        const { data } = await axios.get<AssetApiResponse[]>('/api/assets')
        const nextAssets = Array.isArray(data) ? data.map(normalizeAsset) : []
        syncAssets(nextAssets, true)
        setLastUpdated(new Date())
      } catch {
        // Keep the last good map snapshot during a transient polling failure.
      } finally {
        pollingRef.current = false
      }
    }
    const intervalId = window.setInterval(() => {
      void pollAssets()
    }, 10_000)
    return () => {
      window.clearInterval(intervalId)
      if (highlightTimeoutRef.current !== null) {
        window.clearTimeout(highlightTimeoutRef.current)
      }
    }
  }, [])

  const runFusion = async () => {
    setFusionRunning(true)
    setFusionError(null)
    try {
      await axios.post('/api/v1/fusion/run')
      await loadMapData()
    } catch {
      setFusionError('Could not run fusion. Check connection and try again.')
    } finally {
      setFusionRunning(false)
    }
  }

  const selectAsset = (selected: Pick<SearchAsset, 'id'>) => {
    const asset = assets.find((candidate) => candidate.id === selected.id)
    if (!asset) return

    setSelectedAsset(asset)
  }

  return (
    <section>
      <h1
        style={{
          margin: '0 0 16px',
          color: 'var(--text-1)',
          fontSize: 'var(--font-size-page-title)',
          lineHeight: 1.3,
        }}
      >
        Map
      </h1>

      <div
        style={{
          minHeight: 44,
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 10,
          marginBottom: 16,
        }}
      >
        <button
          type="button"
          onClick={() => void loadMapData()}
          disabled={loading}
          style={{
            minHeight: 44,
            padding: '0 14px',
            border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-sm)',
            background: 'transparent',
            color: 'var(--accent)',
            fontFamily: 'var(--font-sans)',
            fontSize: 13,
            fontWeight: 500,
            cursor: loading ? 'wait' : 'pointer',
            opacity: loading ? 0.7 : 1,
          }}
        >
          Refresh
        </button>
        <button
          type="button"
          onClick={() => void runFusion()}
          disabled={fusionRunning}
          style={{
            minHeight: 44,
            padding: '0 14px',
            border: 0,
            borderRadius: 'var(--radius-sm)',
            background: 'var(--accent)',
            color: 'var(--surface-1)',
            fontFamily: 'var(--font-sans)',
            fontSize: 13,
            fontWeight: 500,
            cursor: fusionRunning ? 'wait' : 'pointer',
            opacity: fusionRunning ? 0.7 : 1,
          }}
        >
          {fusionRunning ? 'Running fusion…' : 'Run fusion'}
        </button>
        <span
          style={{
            marginLeft: 'auto',
            color: 'var(--text-3)',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
          }}
        >
          Last updated: {lastUpdated ? lastUpdated.toLocaleTimeString() : '—'}
        </span>
      </div>
      {fusionError && (
        <p role="alert" style={{ margin: '0 0 12px', color: 'var(--status-conflict)', fontSize: 13 }}>
          {fusionError}
        </p>
      )}

      {loading && (
        <div
          aria-label="Loading map data"
          style={{
            display: 'grid',
            gap: 12,
            maxWidth: 520,
            padding: 12,
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            background: 'var(--surface-1)',
          }}
        >
          {Array.from({ length: 3 }, (_, index) => (
            <div key={index} style={skeletonBarStyle} />
          ))}
        </div>
      )}

      {!loading && error && (
        <div
          role="alert"
          style={{
            maxWidth: 420,
            padding: '16px 18px',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            background: 'var(--surface-1)',
            color: 'var(--text-2)',
          }}
        >
          <p style={{ margin: '0 0 12px', color: 'var(--text-1)' }}>{error}</p>
          <button
            type="button"
            onClick={loadMapData}
            style={{
              minHeight: 44,
              padding: '0 14px',
              border: '1px solid var(--accent)',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--accent)',
              color: 'var(--surface-1)',
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !error && assets.length === 0 && (
        <p
          style={{
            margin: 0,
            padding: 16,
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            background: 'var(--surface-1)',
            color: 'var(--text-2)',
          }}
        >
          No assets found. Seed the database and confirm asset statuses.
        </p>
      )}

      {!loading && !error && (
        <div
          style={{
            position: 'relative',
            minHeight: 'calc(100vh - 144px)',
            display: 'flex',
            alignItems: 'stretch',
            flexWrap: 'wrap',
            gap: 16,
          }}
        >
          <section
            aria-label="Floor map"
            style={{
              position: 'relative',
              minWidth: 0,
              flex: '1 1 600px',
              overflow: 'hidden',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--surface-2)',
            }}
          >
            <FloorMap
              zones={zones}
              assets={assets}
              onSelectAsset={selectAsset}
              highlightedAssetIds={highlightedAssetIds}
            />
          </section>
          <AssetSearch
            selectedAsset={selectedAsset}
            onSelect={selectAsset}
          />
        </div>
      )}

      {selectedAsset && (
        <AssetDetailDrawer
          asset={selectedAsset}
          onClose={() => setSelectedAsset(null)}
        />
      )}
    </section>
  )
}

export default MapPage
