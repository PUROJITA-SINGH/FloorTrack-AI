import axios from 'axios'
import { useEffect, useState } from 'react'
import AlertQueue from '../components/AlertQueue'

type InventoryRow = {
  zone_name: string
  asset_type_name: string
  usable_count: number
  par_count: number
  status: 'ok' | 'deficit'
  deficit_count: number
}

function InventoryPage() {
  const [rows, setRows] = useState<InventoryRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [recommendation, setRecommendation] = useState<InventoryRow | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    axios
      .get<InventoryRow[]>('/api/inventory', { signal: controller.signal })
      .then(({ data }) => {
        setRows(Array.isArray(data) ? data : [])
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [])

  const totalUsable = rows.reduce((sum, row) => sum + row.usable_count, 0)
  const totalPar = rows.reduce((sum, row) => sum + row.par_count, 0)

  return (
    <section>
      <h1 style={titleStyle}>Inventory</h1>
      {error && (
        <p role="alert" style={stateMessageStyle}>
          Could not load inventory. Check connection and try again.
        </p>
      )}
      {!error && !loading && rows.length === 0 && (
        <p style={stateMessageStyle}>
          No inventory data. Seed the database and confirm asset statuses.
        </p>
      )}
      {loading && (
        <div
          role="status"
          aria-label="Loading inventory"
          style={tableShellStyle}
        >
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={headerCellStyle}>Zone</th>
                <th style={headerCellStyle}>Asset Type</th>
                <th style={headerCellStyle}>Usable</th>
                <th style={headerCellStyle}>PAR</th>
                <th style={headerCellStyle}>Status</th>
                <th style={headerCellStyle}>Action</th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 5 }, (_, index) => (
                <tr key={index} aria-hidden="true">
                  <td colSpan={6} style={skeletonCellStyle}>
                    <span style={skeletonBarStyle} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!loading && !error && rows.length > 0 && (
        <>
          <div style={tableShellStyle}>
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th scope="col" style={headerCellStyle}>Zone</th>
                  <th scope="col" style={headerCellStyle}>Asset Type</th>
                  <th scope="col" style={headerCellStyle}>Usable</th>
                  <th scope="col" style={headerCellStyle}>PAR</th>
                  <th scope="col" style={headerCellStyle}>Status</th>
                  <th scope="col" style={headerCellStyle}>Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const deficit = row.usable_count < row.par_count
                  return (
                    <tr
                      key={`${row.zone_name}-${row.asset_type_name}`}
                      style={{
                        background: deficit
                          ? 'var(--accent-subtle)'
                          : 'var(--surface-1)',
                      }}
                    >
                      <td style={cellStyle}>{row.zone_name}</td>
                      <td style={cellStyle}>{row.asset_type_name}</td>
                      <td style={cellStyle}>{row.usable_count}</td>
                      <td style={cellStyle}>{row.par_count}</td>
                      <td style={cellStyle}>
                        <span
                          style={{
                            color: deficit
                              ? 'var(--status-conflict)'
                              : 'var(--status-usable)',
                            fontWeight: 500,
                          }}
                        >
                          {deficit ? 'Deficit' : 'OK'}
                        </span>
                      </td>
                      <td style={cellStyle}>
                        {deficit && (
                          <button
                            type="button"
                            onClick={() => setRecommendation(row)}
                            style={recommendButtonStyle}
                          >
                            Recommend transfer
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
                <tr style={{ background: 'var(--surface-2)', fontWeight: 600 }}>
                  <td colSpan={2} style={cellStyle}>Total</td>
                  <td style={cellStyle}>{totalUsable}</td>
                  <td style={cellStyle}>{totalPar}</td>
                  <td style={cellStyle}>
                    <span
                      style={{
                        color:
                          totalUsable < totalPar
                            ? 'var(--status-conflict)'
                            : 'var(--status-usable)',
                        fontWeight: 600,
                      }}
                    >
                      {totalUsable < totalPar ? 'Deficit' : 'OK'}
                    </span>
                  </td>
                  <td style={cellStyle} />
                </tr>
              </tbody>
            </table>
          </div>
          <p style={unconfirmedNoteStyle}>
            Unconfirmed assets are excluded from usable counts.
          </p>
          {recommendation && (
            <p role="status" style={recommendationStyle}>
              Recommend transferring {recommendation.deficit_count}{' '}
              {recommendation.asset_type_name}
              {recommendation.deficit_count === 1 ? '' : 's'} to{' '}
              {recommendation.zone_name} to meet PAR.
            </p>
          )}
        </>
      )}
      <div style={{ marginTop: 24 }}>
        <AlertQueue />
      </div>
    </section>
  )
}

const titleStyle = {
  margin: '0 0 16px',
  color: 'var(--text-1)',
  fontSize: 'var(--font-size-page-title)',
  lineHeight: 1.3,
} as const

const tableShellStyle = {
  overflowX: 'auto',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  background: 'var(--surface-1)',
} as const

const tableStyle = {
  width: '100%',
  borderCollapse: 'collapse',
  background: 'var(--surface-1)',
  textAlign: 'left',
} as const

const headerCellStyle = {
  padding: '12px 16px',
  borderBottom: '1px solid var(--border)',
  background: 'var(--surface-2)',
  color: 'var(--text-2)',
  fontSize: 13,
  fontWeight: 500,
  whiteSpace: 'nowrap',
} as const

const cellStyle = {
  padding: '12px 16px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-1)',
  fontSize: 14,
} as const

const skeletonCellStyle = {
  height: 52,
  padding: '12px 16px',
  borderBottom: '1px solid var(--border)',
} as const

const skeletonBarStyle = {
  display: 'block',
  width: '65%',
  height: 14,
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface-2)',
  opacity: 0.75,
} as const

const stateMessageStyle = {
  margin: 0,
  padding: 16,
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  background: 'var(--surface-1)',
  color: 'var(--text-2)',
} as const

const recommendButtonStyle = {
  minHeight: 44,
  padding: '0 12px',
  border: 0,
  borderRadius: 'var(--radius-sm)',
  background: 'var(--accent)',
  color: 'var(--surface-1)',
  fontFamily: 'var(--font-sans)',
  fontSize: 13,
  fontWeight: 500,
  whiteSpace: 'nowrap',
  cursor: 'pointer',
} as const

const unconfirmedNoteStyle = {
  margin: '12px 0 0',
  color: 'var(--text-3)',
  opacity: 0.8,
  fontSize: 13,
} as const

const recommendationStyle = {
  margin: '12px 0 0',
  padding: 12,
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface-1)',
  color: 'var(--text-2)',
  fontSize: 14,
} as const

export default InventoryPage
