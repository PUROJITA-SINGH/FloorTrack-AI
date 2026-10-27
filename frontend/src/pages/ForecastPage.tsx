import axios from 'axios'
import { useEffect, useState } from 'react'

type ForecastBand = 'low' | 'moderate' | 'high' | 'critical'

type ForecastResult = {
  demand: number
  projected_usable: number
  shortage_indicator: number
  calibrated: false
  band: ForecastBand
  reason: string
}

const bandColors: Record<ForecastBand, string> = {
  low: 'var(--status-usable)',
  moderate: 'var(--band-med)',
  high: 'var(--status-warn)',
  critical: 'var(--status-conflict)',
}

function ForecastPage() {
  const [forecast, setForecast] = useState<ForecastResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    axios
      .get<ForecastResult>('/api/v1/forecast', {
        params: { horizon_days: 7 },
        signal: controller.signal,
      })
      .then(({ data }) => {
        setForecast(data)
        setError(false)
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [])

  return (
    <section>
      <h1 style={titleStyle}>Forecast</h1>
      {loading ? (
        <p style={textStyle}>Loading forecast…</p>
      ) : error || !forecast ? (
        <p role="alert" style={textStyle}>
          Could not load forecast data. Check connection and try again.
        </p>
      ) : (
        <section
          aria-label="Shortage indicator"
          style={{
            maxWidth: 560,
            padding: 20,
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            background: 'var(--surface-1)',
            color: 'var(--text-1)',
          }}
        >
          <div style={{ color: 'var(--text-2)', fontSize: 14 }}>
            Shortage indicator · Not a probability
          </div>
          <div
            style={{
              marginTop: 8,
              color: bandColors[forecast.band],
              fontSize: 36,
              fontWeight: 600,
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {(forecast.shortage_indicator * 100).toFixed(0)}%
          </div>
          <div
            style={{
              display: 'inline-flex',
              marginTop: 8,
              padding: '4px 10px',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--surface-2)',
              color: bandColors[forecast.band],
              fontSize: 13,
              fontWeight: 600,
              textTransform: 'capitalize',
            }}
          >
            {forecast.band}
          </div>
          <dl
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr auto',
              gap: '8px 16px',
              margin: '20px 0 0',
            }}
          >
            <dt style={{ color: 'var(--text-2)' }}>Demand (7 days)</dt>
            <dd style={valueStyle}>{forecast.demand}</dd>
            <dt style={{ color: 'var(--text-2)' }}>Projected usable</dt>
            <dd style={valueStyle}>{forecast.projected_usable}</dd>
            <dt style={{ color: 'var(--text-2)' }}>Calibrated</dt>
            <dd style={valueStyle}>false</dd>
          </dl>
          <p style={{ ...textStyle, marginTop: 16 }}>{forecast.reason}</p>
        </section>
      )}
    </section>
  )
}

const titleStyle = {
  margin: '0 0 16px',
  color: 'var(--text-1)',
  fontSize: 'var(--font-size-page-title)',
  lineHeight: 1.3,
} as const

const textStyle = {
  margin: 0,
  color: 'var(--text-2)',
} as const

const valueStyle = {
  margin: 0,
  color: 'var(--text-1)',
  fontVariantNumeric: 'tabular-nums',
  textAlign: 'right',
} as const

export default ForecastPage
