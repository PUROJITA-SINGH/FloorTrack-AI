import axios from 'axios'
import { useEffect, useState } from 'react'

export type SearchAsset = {
  id: string
  code: string
  asset_type?: string | null
  zone?: string | null
}

type AssetSearchProps = {
  selectedAsset: SearchAsset | null
  onSelect: (asset: SearchAsset) => void
}

const searchInputStyle = {
  width: '100%',
  minHeight: 42,
  padding: '0 12px',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface-2)',
  color: 'var(--text-1)',
  fontFamily: 'var(--font-sans)',
  fontSize: 15,
} as const

function AssetSearch({ selectedAsset, onSelect }: AssetSearchProps) {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  // The latest finished search, tagged with the query it answered. Loading,
  // error and results are derived from it, so no state is set synchronously
  // inside an effect.
  const [searchState, setSearchState] = useState<{
    query: string
    results: SearchAsset[]
    error: boolean
  } | null>(null)
  const searchReady = searchState?.query === debouncedQuery
  const loading = Boolean(debouncedQuery) && !searchReady
  const error = Boolean(debouncedQuery) && searchReady && searchState.error
  const results =
    debouncedQuery && searchReady && !searchState.error ? searchState.results : []

  useEffect(() => {
    const timeoutId = window.setTimeout(() => setDebouncedQuery(query.trim()), 300)
    return () => window.clearTimeout(timeoutId)
  }, [query])

  useEffect(() => {
    if (!debouncedQuery) return

    const controller = new AbortController()

    axios
      .get<SearchAsset[]>('/api/assets', {
        params: { search: debouncedQuery },
        signal: controller.signal,
      })
      .then(({ data }) => {
        setSearchState({
          query: debouncedQuery,
          results: Array.isArray(data) ? data : [],
          error: false,
        })
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setSearchState({ query: debouncedQuery, results: [], error: true })
        }
      })

    return () => controller.abort()
  }, [debouncedQuery])

  return (
    <section
      aria-label="Asset search"
      style={{
        width: 320,
        flex: '0 0 320px',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        background: 'var(--surface-1)',
      }}
    >
      <div style={{ padding: 16, borderBottom: '1px solid var(--border)' }}>
        <label
          htmlFor="asset-search-input"
          style={{
            display: 'block',
            marginBottom: 8,
            color: 'var(--text-1)',
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          Find an asset
        </label>
        <input
          id="asset-search-input"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by asset ID or tag"
          style={searchInputStyle}
        />
      </div>

      <div aria-live="polite" style={{ flex: 1, overflowY: 'auto' }}>
        {loading && (
          <div
            role="status"
            style={{
              display: 'flex',
              minHeight: 56,
              alignItems: 'center',
              gap: 10,
              padding: '12px 16px',
              color: 'var(--accent)',
              fontSize: 13,
            }}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <circle
                cx="9"
                cy="9"
                r="7"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeDasharray="30 14"
                strokeLinecap="round"
              >
                <animateTransform
                  attributeName="transform"
                  type="rotate"
                  from="0 9 9"
                  to="360 9 9"
                  dur="0.9s"
                  repeatCount="indefinite"
                />
              </circle>
            </svg>
            <span>Searching assets</span>
          </div>
        )}

        {!loading && error && (
          <p style={messageStyle}>
            Could not reach the asset service. Check connection and try again.
          </p>
        )}

        {!loading && !error && debouncedQuery && results.length === 0 && (
          <p style={messageStyle}>
            No results found. Try a different asset ID or tag.
          </p>
        )}

        {!loading &&
          !error &&
          results.map((asset) => {
            const isSelected = selectedAsset?.id === asset.id
            return (
              <button
                key={asset.id}
                type="button"
                onClick={() => onSelect(asset)}
                aria-pressed={isSelected}
                style={{
                  width: '100%',
                  minHeight: 56,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'stretch',
                  justifyContent: 'center',
                  gap: 2,
                  padding: '8px 16px',
                  border: 0,
                  borderBottom: '1px solid var(--border)',
                  color: 'var(--text-1)',
                  background: isSelected
                    ? 'var(--accent-subtle)'
                    : 'var(--surface-1)',
                  textAlign: 'left',
                  cursor: 'pointer',
                }}
                onMouseEnter={(event) => {
                  if (!isSelected) {
                    event.currentTarget.style.background = 'var(--surface-2)'
                  }
                }}
                onMouseLeave={(event) => {
                  if (!isSelected) {
                    event.currentTarget.style.background = 'var(--surface-1)'
                  }
                }}
              >
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 14,
                    fontWeight: 500,
                  }}
                >
                  {asset.code}
                </span>
                <span style={{ color: 'var(--text-2)', fontSize: 13 }}>
                  {asset.asset_type ?? 'Unknown type'}
                </span>
                <span style={{ color: 'var(--text-3)', fontSize: 13 }}>
                  {asset.zone ?? 'Zone unknown'}
                </span>
              </button>
            )
          })}
      </div>
    </section>
  )
}

const messageStyle = {
  margin: 0,
  padding: '16px',
  color: 'var(--text-2)',
  fontSize: 13,
} as const

export default AssetSearch
