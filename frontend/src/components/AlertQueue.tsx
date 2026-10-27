import axios from 'axios'
import { useEffect, useState } from 'react'

type AlertItem = {
  id: string
  severity: string
  title: string
  message: string
  zone_name: string
  created_at: string
  status: string
}

function AlertQueue() {
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [busyAlertId, setBusyAlertId] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const fetchAlerts = async () => {
      try {
        const { data } = await axios.get<AlertItem[]>('/api/alerts', {
          params: { status: 'open' },
          signal: controller.signal,
        })
        setAlerts(Array.isArray(data) ? data : [])
        setError(false)
      } catch {
        if (!controller.signal.aborted) setError(true)
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }

    void fetchAlerts()
    const intervalId = window.setInterval(() => void fetchAlerts(), 30_000)
    return () => {
      controller.abort()
      window.clearInterval(intervalId)
    }
  }, [])

  const acknowledge = async (alertId: string) => {
    setBusyAlertId(alertId)
    try {
      await axios.post(`/api/alerts/${encodeURIComponent(alertId)}/acknowledge`, {
        actor: 'demo_admin',
      })
      setAlerts((current) => current.filter((alert) => alert.id !== alertId))
    } catch {
      setError(true)
    } finally {
      setBusyAlertId(null)
    }
  }

  const dismiss = async (alertId: string) => {
    setBusyAlertId(alertId)
    try {
      await axios.post(`/api/alerts/${encodeURIComponent(alertId)}/dismiss`)
      setAlerts((current) => current.filter((alert) => alert.id !== alertId))
    } catch {
      setError(true)
    } finally {
      setBusyAlertId(null)
    }
  }

  return (
    <section aria-label="Open alerts">
      <h2 style={headingStyle}>Open alerts</h2>
      {loading && (
        <div role="status" aria-label="Loading alerts" style={listStyle}>
          {Array.from({ length: 3 }, (_, index) => (
            <div key={index} style={skeletonCardStyle}>
              <span style={skeletonLineStyle} />
              <span style={{ ...skeletonLineStyle, width: '80%' }} />
              <span style={{ ...skeletonLineStyle, width: '45%' }} />
            </div>
          ))}
        </div>
      )}
      {!loading && error && (
        <p role="alert" style={messageStyle}>
          Could not load alerts. Check connection and try again.
        </p>
      )}
      {!loading && !error && alerts.length === 0 && (
        <p style={messageStyle}>
          No open alerts. PAR levels are met across all zones.
        </p>
      )}
      {!loading && !error && alerts.length > 0 && (
        <div style={listStyle}>
          {alerts.map((alert) => {
            const severity = alert.severity.toLowerCase()
            const severityColor =
              severity === 'high'
                ? 'var(--status-conflict)'
                : severity === 'medium'
                  ? 'var(--status-warn)'
                  : 'var(--text-3)'
            return (
              <article
                key={alert.id}
                style={{
                  ...cardStyle,
                  borderLeft: `4px solid ${severityColor}`,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: 12,
                  }}
                >
                  <h3 style={titleStyle}>{alert.title}</h3>
                  <span
                    style={{
                      ...badgeStyle,
                      color: severityColor,
                    }}
                  >
                    {severity.toUpperCase()}
                  </span>
                </div>
                <p style={bodyStyle}>{alert.message}</p>
                <div style={metadataStyle}>
                  <span>{alert.zone_name}</span>
                  <time
                    dateTime={alert.created_at}
                    style={{ fontFamily: 'var(--font-mono)' }}
                  >
                    {formatTimestamp(alert.created_at)}
                  </time>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <button
                    type="button"
                    disabled={busyAlertId === alert.id}
                    onClick={() => void acknowledge(alert.id)}
                    style={acknowledgeButtonStyle}
                  >
                    {busyAlertId === alert.id ? 'Acknowledging…' : 'Acknowledge'}
                  </button>
                  <button
                    type="button"
                    disabled={busyAlertId === alert.id}
                    onClick={() => void dismiss(alert.id)}
                    style={dismissButtonStyle}
                  >
                    {busyAlertId === alert.id ? 'Updating…' : 'Dismiss'}
                  </button>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}

function formatTimestamp(value: string): string {
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleString() : 'Unknown time'
}

const headingStyle = {
  margin: '0 0 12px',
  color: 'var(--text-1)',
  fontSize: 'var(--font-size-section-heading)',
  fontWeight: 600,
} as const

const listStyle = {
  display: 'grid',
  gap: 12,
} as const

const cardStyle = {
  padding: 14,
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  background: 'var(--surface-1)',
} as const

const titleStyle = {
  margin: 0,
  color: 'var(--text-1)',
  fontSize: 15,
  fontWeight: 500,
} as const

const badgeStyle = {
  flex: '0 0 auto',
  fontSize: 12,
  fontWeight: 600,
} as const

const bodyStyle = {
  margin: '8px 0',
  color: 'var(--text-2)',
  fontSize: 13,
} as const

const metadataStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  gap: 8,
  color: 'var(--text-3)',
  fontSize: 12,
} as const

const acknowledgeButtonStyle = {
  minHeight: 44,
  padding: '0 12px',
  border: '1px solid var(--accent)',
  borderRadius: 'var(--radius-sm)',
  background: 'transparent',
  color: 'var(--accent)',
  fontFamily: 'var(--font-sans)',
  fontSize: 13,
  fontWeight: 500,
  cursor: 'pointer',
} as const

const dismissButtonStyle = {
  minHeight: 44,
  padding: '0 12px',
  border: 0,
  background: 'transparent',
  color: 'var(--text-2)',
  fontFamily: 'var(--font-sans)',
  fontSize: 13,
  cursor: 'pointer',
} as const

const messageStyle = {
  margin: 0,
  padding: 16,
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  background: 'var(--surface-1)',
  color: 'var(--text-2)',
  fontSize: 14,
} as const

const skeletonCardStyle = {
  display: 'grid',
  gap: 10,
  padding: 16,
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  background: 'var(--surface-1)',
} as const

const skeletonLineStyle = {
  display: 'block',
  width: '60%',
  height: 14,
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface-2)',
} as const

export default AlertQueue
