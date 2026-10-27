import axios from 'axios'
import { X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

type Alert = {
  id: string
  title: string
  message?: string
  recommendation?: string
  status?: string
}

type FusionDetail = {
  camera_zone?: string | null
  ble_zone?: string | null
  gateway_count?: number | null
  ble_quality?: number | null
  reason?: string | null
  confidence_breakdown?: Record<string, number> | null
  evidence_links?: EvidenceLink[] | null
  rssi_spread?: number | null
  calibration?: { note?: string; tx_power?: number; path_loss_exponent?: number } | null
}

type EvidenceLink = {
  source: string
  event_id: string
  href: string
}

type HistoryEntry = {
  timestamp: string
  from_zone: string | null
  to_zone: string | null
  confidence_band: string | null
  decision_status: string | null
  reason: string | null
  evidence_links: EvidenceLink[]
}

type AssetDetail = {
  id: string
  code: string
  zone?: string | null
  zone_id?: string | null
  confidence_band?: string | null
  decision_status?: string | null
  freshness?: number | null
  camera_coverage?: number | null
  camera_last_seen?: string | null
  last_fusion_at?: string | null
  location_updated_at?: string | null
  updated_at?: string | null
  confidence_breakdown?: Record<string, number> | null
  camera_zone?: string | null
  camera_zone_name?: string | null
  ble_zone?: string | null
  ble_zone_name?: string | null
  gateway_count?: number | null
  decision_reason?: string | null
  disagreement_reason?: string | null
  fusion_detail?: FusionDetail | null
  evidence_links?: EvidenceLink[] | null
  operational_status?: string | null
  status_source?: string | null
  status_actor?: string | null
  status_reason?: string | null
  status_confirmed_at?: string | null
  status_stale_after?: string | null
  alerts?: Alert[]
}

type AssetDetailDrawerProps = {
  asset: AssetDetail
  onClose: () => void
}

const bandColor: Record<string, string> = {
  high: 'var(--band-high)',
  medium: 'var(--band-med)',
  low: 'var(--band-low)',
  stale: 'var(--text-3)',
}

const breakdownLabels: Record<string, string> = {
  camera_confidence: 'Camera confidence',
  ble_quality: 'BLE quality',
  zone_agreement: 'Zone agreement',
  freshness: 'Freshness',
  coverage: 'Coverage',
  conflict_penalty: 'Conflict penalty',
  stale_penalty: 'Stale penalty',
}

const breakdownKeys = Object.keys(breakdownLabels)

function relativeTime(value: string | null | undefined, now: number): string {
  if (!value) return 'Unknown'
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) return 'Unknown'

  const seconds = Math.round((timestamp - now) / 1000)
  const absoluteSeconds = Math.abs(seconds)
  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  if (absoluteSeconds < 60) return formatter.format(seconds, 'second')
  if (absoluteSeconds < 3600) return formatter.format(Math.round(seconds / 60), 'minute')
  if (absoluteSeconds < 86400) return formatter.format(Math.round(seconds / 3600), 'hour')
  return formatter.format(Math.round(seconds / 86400), 'day')
}

function displayLabel(value?: string | null): string {
  if (!value) return 'Unknown'
  return value
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

function AssetDetailDrawer({ asset, onClose }: AssetDetailDrawerProps) {
  const drawerRef = useRef<HTMLElement>(null)
  const [confirmedAsset, setConfirmedAsset] = useState<
    | (Pick<
        AssetDetail,
        | 'id'
        | 'operational_status'
        | 'status_source'
        | 'status_confirmed_at'
        | 'status_stale_after'
        | 'status_actor'
        | 'status_reason'
      >)
    | null
  >(null)
  const [detailsState, setDetailsState] = useState<{
    key: string
    data: AssetDetail | null
    error: boolean
  } | null>(null)
  const [historyState, setHistoryState] = useState<{
    key: string
    entries: HistoryEntry[]
    error: boolean
  } | null>(null)
  const [refreshRequest, setRefreshRequest] = useState(0)
  const [showQuality, setShowQuality] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [confirmationError, setConfirmationError] = useState('')
  const [alertState, setAlertState] = useState<{
    assetId: string
    alerts: Alert[]
  } | null>(null)
  const [now, setNow] = useState(0)
  // Loading and error flags are derived from the request key instead of being
  // set synchronously inside effects: a result only counts when its key matches
  // the asset (and refresh request) currently being shown.
  const detailsKey = `${asset.id}|${asset.last_fusion_at ?? ''}|${asset.updated_at ?? ''}|${refreshRequest}`
  const historyKey = `${asset.id}|${asset.last_fusion_at ?? ''}`
  const detailsReady = detailsState?.key === detailsKey
  const detailsLoading = !detailsReady
  const detailsError = detailsReady && detailsState.error
  const fetchedAsset = detailsReady ? detailsState.data : null
  const historyReady = historyState?.key === historyKey
  const historyLoading = !historyReady
  const historyError = historyReady && historyState.error
  const history = historyReady ? historyState.entries : []
  const currentAsset = {
    ...fetchedAsset,
    ...asset,
    ...(confirmedAsset?.id === asset.id ? confirmedAsset : null),
  }
  const alerts =
    alertState?.assetId === asset.id ? alertState.alerts : asset.alerts ?? []
  const openAlerts = alerts.filter((alert) => !alert.status || alert.status === 'open')

  useEffect(() => {
    const timeoutId = window.setTimeout(() => setNow(Date.now()), 0)
    const intervalId = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => {
      window.clearTimeout(timeoutId)
      window.clearInterval(intervalId)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()

    axios
      .get<AssetDetail>(`/api/assets/${encodeURIComponent(asset.id)}`, {
        signal: controller.signal,
      })
      .then(({ data }) => {
        setDetailsState({ key: detailsKey, data, error: false })
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setDetailsState({ key: detailsKey, data: null, error: true })
        }
      })

    return () => controller.abort()
  }, [asset.id, detailsKey])

  useEffect(() => {
    const controller = new AbortController()

    axios
      .get<HistoryEntry[]>(`/api/assets/${encodeURIComponent(asset.id)}/history`, {
        signal: controller.signal,
      })
      .then(({ data }) => {
        setHistoryState({
          key: historyKey,
          entries: Array.isArray(data) ? data : [],
          error: false,
        })
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setHistoryState({ key: historyKey, entries: [], error: true })
        }
      })

    return () => controller.abort()
  }, [asset.id, historyKey])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    const handlePointerDown = (event: PointerEvent) => {
      if (
        event.target instanceof Node &&
        !drawerRef.current?.contains(event.target)
      ) {
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('pointerdown', handlePointerDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('pointerdown', handlePointerDown)
    }
  }, [onClose])

  const band = currentAsset.confidence_band?.toLowerCase() ?? 'stale'
  const color = bandColor[band] ?? 'var(--band-low)'
  const isConflict = currentAsset.decision_status === 'sensor_disagreement'
  const statusStaleAfter = currentAsset.status_stale_after
    ? Date.parse(currentAsset.status_stale_after)
    : Number.NaN
  const isStatusStale =
    now > 0 && Number.isFinite(statusStaleAfter) && statusStaleAfter < now
  const breakdown =
    currentAsset.fusion_detail?.confidence_breakdown ??
    currentAsset.confidence_breakdown
  const lastUpdated =
    currentAsset.last_fusion_at ??
    currentAsset.location_updated_at ??
    currentAsset.updated_at
  const cameraLastSeenAt = currentAsset.camera_last_seen
    ? Date.parse(currentAsset.camera_last_seen)
    : Number.NaN
  const hasRecentCameraData =
    now > 0 &&
    Number.isFinite(cameraLastSeenAt) &&
    now - cameraLastSeenAt <= 30 * 60 * 1000
  const cameraZone =
    currentAsset.fusion_detail?.camera_zone ??
    currentAsset.camera_zone_name ??
    currentAsset.camera_zone
  const bleZone =
    currentAsset.fusion_detail?.ble_zone ??
    currentAsset.ble_zone_name ??
    currentAsset.ble_zone
  const gatewayCount =
    currentAsset.fusion_detail?.gateway_count ?? currentAsset.gateway_count
  const rssiSpread = currentAsset.fusion_detail?.rssi_spread
  const calibration = currentAsset.fusion_detail?.calibration
  const evidenceLinks =
    currentAsset.fusion_detail?.evidence_links ??
    currentAsset.evidence_links ??
    []
  const decisionReason =
    currentAsset.disagreement_reason ??
    currentAsset.fusion_detail?.reason ?? currentAsset.decision_reason
  const bleQuality = currentAsset.fusion_detail?.ble_quality

  const confirmAvailable = async () => {
    setConfirming(true)
    setConfirmationError('')
    const actor = import.meta.env.VITE_DEMO_ACTOR || 'demo_operator'
    const reason = 'Confirmed from asset detail drawer'
    try {
      const { data } = await axios.post(
        `/api/assets/${encodeURIComponent(currentAsset.id)}/operational-status`,
        {
          status: 'available',
          source: 'user',
          actor,
          reason,
        },
      )
      setConfirmedAsset({
        id: currentAsset.id,
        operational_status: data.status,
        status_source: data.source,
        status_confirmed_at: data.confirmed_at,
        status_stale_after: data.stale_after,
        status_actor: actor,
        status_reason: reason,
      })
      setRefreshRequest((request) => request + 1)
    } catch {
      setConfirmationError('Could not confirm status. Try again.')
    } finally {
      setConfirming(false)
    }
  }

  const setAlertStatus = (alertId: string, status: 'acknowledged' | 'dismissed') => {
    const updatedAlerts =
      status === 'dismissed'
        ? alerts.filter((alert) => alert.id !== alertId)
        : alerts.map((alert) =>
            alert.id === alertId ? { ...alert, status } : alert,
          )
    setAlertState({ assetId: asset.id, alerts: updatedAlerts })
  }

  return (
    <aside
      ref={drawerRef}
      className="asset-detail-drawer"
      aria-label={`Details for ${currentAsset.code}`}
      aria-modal="false"
      role="complementary"
      style={{
        position: 'fixed',
        zIndex: 2,
        top: 60,
        right: 0,
        bottom: 0,
        display: 'flex',
        width: 320,
        maxWidth: '100%',
        flexDirection: 'column',
        overflow: 'hidden',
        borderRadius: 'var(--radius-md) 0 0 var(--radius-md)',
        background: 'var(--surface-1)',
        boxShadow: 'var(--shadow-sm)',
        color: 'var(--text-1)',
      }}
    >
      <header
        style={{
          minHeight: 60,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 16px',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <div>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--font-size-asset-id)',
              fontWeight: 500,
            }}
          >
            {currentAsset.code}
          </div>
          <div style={{ color: 'var(--text-2)', fontSize: 13 }}>
            {currentAsset.zone ?? 'Zone unknown'}
          </div>
        </div>
        <button
          type="button"
          aria-label="Close asset details"
          onClick={onClose}
          onMouseEnter={(event) => {
            event.currentTarget.style.color = 'var(--text-1)'
          }}
          onMouseLeave={(event) => {
            event.currentTarget.style.color = 'var(--text-2)'
          }}
          style={{
            width: 44,
            height: 44,
            display: 'grid',
            placeItems: 'center',
            border: 0,
            borderRadius: 'var(--radius-sm)',
            background: 'transparent',
            color: 'var(--text-2)',
            cursor: 'pointer',
          }}
        >
          <X size={20} strokeWidth={1.8} aria-hidden="true" />
        </button>
      </header>

      {detailsLoading ? (
        <div
          role="status"
          aria-label="Loading asset details"
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 10,
            padding: 16,
            color: 'var(--text-2)',
            fontSize: 13,
          }}
        >
          <span className="asset-detail-spinner" aria-hidden="true" />
          Loading asset details
        </div>
      ) : detailsError ? (
        <div
          role="alert"
          style={{ padding: 16, color: 'var(--text-2)', fontSize: 13 }}
        >
          <p style={{ margin: '0 0 12px' }}>
            Could not load asset details. Try again.
          </p>
          <button
            type="button"
            onClick={() => setRefreshRequest((request) => request + 1)}
            style={secondaryButtonStyle}
          >
            Retry
          </button>
        </div>
      ) : (
      <div style={{ overflowY: 'auto' }}>
        <section
          aria-labelledby="asset-location-heading"
          style={{ padding: 16, background: 'var(--surface-1)' }}
        >
          <h2 style={headingStyle} id="asset-location-heading">
            Location
          </h2>
          <div style={{ fontSize: 15 }}>{currentAsset.zone ?? 'Zone unknown'}</div>
          <div style={metaStyle}>Last updated: {relativeTime(lastUpdated, now)}</div>
          <div style={metaStyle}>
            Freshness:{' '}
            {typeof currentAsset.freshness === 'number'
              ? `${Math.round(currentAsset.freshness)} seconds since estimate`
              : 'No location estimate'}
          </div>
          <div style={metaStyle}>
            Camera coverage:{' '}
            {typeof currentAsset.camera_coverage === 'number'
              ? `${currentAsset.camera_coverage}%`
              : '—'}
          </div>
          {!hasRecentCameraData ? (
            <div style={{ ...metaStyle, color: 'var(--status-warn)' }}>
              No recent camera data
            </div>
          ) : (
            <div style={metaStyle}>
              Last camera data: {relativeTime(currentAsset.camera_last_seen, now)}
            </div>
          )}
          <a href="/" style={linkStyle}>
            View on map
          </a>
        </section>

        <section
          aria-labelledby="asset-confidence-heading"
          style={{
            padding: 16,
            borderTop: '1px solid var(--border)',
            background: 'var(--accent-subtle)',
          }}
        >
          <h2 style={headingStyle} id="asset-confidence-heading">
            Confidence
          </h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            <span
              style={{
                ...chipStyle,
                color,
                background: `color-mix(in srgb, ${color} 10%, transparent)`,
              }}
            >
              {band.toUpperCase()}
            </span>
            {isConflict && (
              <span
                style={{
                  ...chipStyle,
                  color: 'var(--surface-1)',
                  background: 'var(--status-conflict)',
                }}
              >
                Sensor disagreement
              </span>
            )}
          </div>

          <button
            type="button"
            aria-expanded={showQuality}
            onClick={() => setShowQuality((visible) => !visible)}
            style={textButtonStyle}
          >
            {showQuality ? 'Hide quality factors' : 'View quality factors'}
          </button>
          {showQuality && (
            <dl
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr auto',
                gap: '6px 12px',
                margin: '8px 0 0',
                fontSize: 13,
              }}
            >
              {breakdownKeys.map((key) => {
                const value = breakdown?.[key]
                return (
                  <div key={key} style={{ display: 'contents' }}>
                    <dt style={{ color: 'var(--text-2)' }}>
                      {breakdownLabels[key]}
                    </dt>
                    <dd style={{ margin: 0, fontVariantNumeric: 'tabular-nums' }}>
                      {typeof value === 'number' ? value.toFixed(2) : '—'}
                    </dd>
                  </div>
                )
              })}
            </dl>
          )}

          <div style={{ marginTop: 10, color: 'var(--text-2)', fontSize: 13 }}>
            {cameraZone && <div>Camera: {cameraZone}</div>}
            {bleZone && (
              <div>
                BLE: {bleZone}
                {gatewayCount != null
                  ? ` (${gatewayCount} gateways)`
                  : ''}
              </div>
            )}
            {bleQuality != null && <div>BLE quality: {bleQuality.toFixed(2)}</div>}
            {rssiSpread != null && (
              <div>RSSI spread: {rssiSpread.toFixed(1)} dBm</div>
            )}
            {calibration?.note && <div>Calibration: {calibration.note}</div>}
            {evidenceLinks.length > 0 && (
              <div style={{ display: 'grid', gap: 4, marginTop: 8 }}>
                <strong>Evidence</strong>
                {evidenceLinks.map((evidence) => (
                  <a
                    key={`${evidence.source}-${evidence.event_id}`}
                    href={evidence.href}
                    target="_blank"
                    rel="noreferrer"
                    style={linkStyle}
                  >
                    {displayLabel(evidence.source)} event {evidence.event_id}
                  </a>
                ))}
              </div>
            )}
            {isConflict && (
              <div style={{ marginTop: 6, color: 'var(--text-2)', fontSize: 13 }}>
                {decisionReason ?? 'Sensors report different zones'}
              </div>
            )}
          </div>
        </section>

        <section
          aria-labelledby="asset-history-heading"
          style={{ padding: 16, borderTop: '1px solid var(--border)' }}
        >
          <h2 style={headingStyle} id="asset-history-heading">
            Location history
          </h2>
          {historyLoading ? (
            <p style={metaStyle}>Loading location history…</p>
          ) : historyError ? (
            <p role="alert" style={{ ...metaStyle, color: 'var(--status-conflict)' }}>
              Could not load location history.
            </p>
          ) : history.length === 0 ? (
            <p style={metaStyle}>No confirmed location changes recorded.</p>
          ) : (
            <ol style={{ margin: 0, paddingLeft: 20 }}>
              {history.map((entry, index) => (
                <li
                  key={`${entry.timestamp}-${entry.to_zone ?? 'unknown'}-${index}`}
                  style={{ padding: '6px 0', color: 'var(--text-2)', fontSize: 13 }}
                >
                  <div>
                    {entry.from_zone ?? 'Unknown'} → {entry.to_zone ?? 'Unknown'}
                  </div>
                  <div style={metaStyle}>
                    {relativeTime(entry.timestamp, now)} ·{' '}
                    {displayLabel(entry.confidence_band)} confidence
                  </div>
                  {entry.reason && <div style={metaStyle}>{entry.reason}</div>}
                  {entry.evidence_links.map((evidence) => (
                    <a
                      key={`${evidence.source}-${evidence.event_id}`}
                      href={evidence.href}
                      target="_blank"
                      rel="noreferrer"
                      style={linkStyle}
                    >
                      {displayLabel(evidence.source)} evidence
                    </a>
                  ))}
                </li>
              ))}
            </ol>
          )}
        </section>

        <section
          aria-labelledby="asset-status-heading"
          style={{
            padding: 16,
            borderTop: '1px solid var(--border)',
            background: 'var(--surface-2)',
          }}
        >
          <h2 style={headingStyle} id="asset-status-heading">
            Operational status
          </h2>
          <span
            title={[
              currentAsset.operational_status !== 'status_unknown' && currentAsset.status_source
                ? `Source: ${currentAsset.status_source}`
                : '',
              currentAsset.status_confirmed_at
                ? `Confirmed: ${new Date(currentAsset.status_confirmed_at).toLocaleString()}`
                : 'Not confirmed',
            ]
              .filter(Boolean)
              .join(' · ')}
            style={{
              ...chipStyle,
              color: statusColor(currentAsset.operational_status),
              background: 'var(--surface-1)',
            }}
          >
            {displayStatus(currentAsset.operational_status)}
          </span>
          {isStatusStale && (
            <span
              style={{
                ...chipStyle,
                marginLeft: 8,
                color: 'var(--status-warn)',
                background: 'var(--surface-1)',
              }}
            >
              Unconfirmed
            </span>
          )}
          {currentAsset.operational_status !== 'status_unknown' &&
          currentAsset.status_confirmed_at &&
          (currentAsset.status_actor || currentAsset.status_source) ? (
            <div style={{ ...metaStyle, color: 'var(--text-2)' }}>
              Confirmed by{' '}
              {currentAsset.status_actor ??
                (currentAsset.status_source === 'workflow_adapter'
                  ? 'workflow adapter'
                  : 'user')}
            </div>
          ) : (
            <div style={{ ...metaStyle, color: 'var(--text-2)' }}>
              Not confirmed
            </div>
          )}
          {currentAsset.status_reason && (
            <div style={{ ...metaStyle, color: 'var(--text-2)' }}>
              Reason: {currentAsset.status_reason}
            </div>
          )}
          {currentAsset.status_confirmed_at && (
            <div
              style={{
                ...metaStyle,
                fontFamily: 'var(--font-mono)',
              }}
            >
              {new Date(currentAsset.status_confirmed_at).toLocaleString()}
            </div>
          )}
          <button
            type="button"
            onClick={confirmAvailable}
            disabled={confirming}
            style={{
              minHeight: 44,
              marginTop: 12,
              padding: '0 14px',
              border: 0,
              borderRadius: 'var(--radius-sm)',
              background: 'var(--accent)',
              color: 'var(--surface-1)',
              fontFamily: 'var(--font-sans)',
              fontSize: 15,
              fontWeight: 500,
              cursor: confirming ? 'wait' : 'pointer',
              opacity: confirming ? 0.7 : 1,
            }}
          >
            {confirming ? 'Confirming…' : 'Confirm available'}
          </button>
          {confirmationError && (
            <p role="alert" style={{ ...metaStyle, color: 'var(--status-conflict)' }}>
              {confirmationError}
            </p>
          )}
        </section>

        {openAlerts.length > 0 && (
          <section
            aria-labelledby="asset-alerts-heading"
            style={{
              padding: 16,
              borderTop: '1px solid var(--border)',
              background: 'var(--surface-1)',
            }}
          >
            <h2 style={headingStyle} id="asset-alerts-heading">
              Alerts
            </h2>
            {openAlerts.map((alert) => (
              <article
                key={alert.id}
                style={{
                  padding: '12px 0',
                  borderTop: '1px solid var(--border)',
                }}
              >
                <h3 style={{ margin: '0 0 4px', fontSize: 15, fontWeight: 600 }}>
                  {alert.title}
                </h3>
                <p style={{ margin: 0, color: 'var(--text-2)', fontSize: 13 }}>
                  {alert.recommendation ?? alert.message}
                </p>
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  {alert.status !== 'acknowledged' && (
                    <button
                      type="button"
                      onClick={() => setAlertStatus(alert.id, 'acknowledged')}
                      style={secondaryButtonStyle}
                    >
                      Acknowledge
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setAlertStatus(alert.id, 'dismissed')}
                    style={secondaryButtonStyle}
                  >
                    Dismiss
                  </button>
                </div>
              </article>
            ))}
          </section>
        )}
      </div>
      )}
    </aside>
  )
}

function statusColor(status?: string | null): string {
  if (status === 'available' || status === 'confirmed') return 'var(--status-usable)'
  if (!status || status === 'status_unknown' || status === 'unknown') return 'var(--text-3)'
  if (status === 'status_stale' || status === 'stale') return 'var(--status-warn)'
  return 'var(--text-2)'
}

function displayStatus(status?: string | null): string {
  if (!status) return 'Unknown'
  return displayLabel(status.replace(/^status_/, ''))
}

const headingStyle = {
  margin: '0 0 10px',
  color: 'var(--text-1)',
  fontSize: 'var(--font-size-section-heading)',
  lineHeight: 1.3,
  fontWeight: 600,
} as const

const metaStyle = {
  marginTop: 6,
  color: 'var(--text-3)',
  fontSize: 13,
} as const

const chipStyle = {
  minHeight: 26,
  display: 'inline-flex',
  alignItems: 'center',
  padding: '3px 8px',
  borderRadius: 'var(--radius-sm)',
  fontSize: 12,
  fontWeight: 600,
  lineHeight: 1.2,
} as const

const linkStyle = {
  display: 'inline-flex',
  minHeight: 44,
  alignItems: 'center',
  color: 'var(--accent)',
  fontSize: 13,
  textDecoration: 'none',
} as const

const textButtonStyle = {
  minHeight: 44,
  padding: '0 4px',
  border: 0,
  background: 'transparent',
  color: 'var(--accent)',
  fontFamily: 'var(--font-sans)',
  fontSize: 13,
  cursor: 'pointer',
} as const

const secondaryButtonStyle = {
  minHeight: 44,
  padding: '0 10px',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface-1)',
  color: 'var(--text-2)',
  fontFamily: 'var(--font-sans)',
  fontSize: 13,
  cursor: 'pointer',
} as const

export default AssetDetailDrawer
