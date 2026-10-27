function SensorHealthPage() {
  return (
    <section>
      <h1 style={titleStyle}>Sensor Health</h1>
      <p style={textStyle}>Sensor health details are coming soon.</p>
      <section
        aria-labelledby="camera-coverage-heading"
        style={{
          maxWidth: 680,
          marginTop: 16,
          padding: 16,
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          background: 'var(--surface-1)',
        }}
      >
        <h2
          id="camera-coverage-heading"
          style={{
            margin: '0 0 8px',
            color: 'var(--text-1)',
            fontSize: 'var(--font-size-section-heading)',
          }}
        >
          Camera coverage and freshness
        </h2>
        <p style={{ ...textStyle, fontSize: 13 }}>
          Camera silence is reported as coverage and data staleness only. It does
          not indicate a missing asset or change an asset&apos;s location,
          confidence band, or operational status.
        </p>
      </section>
    </section>
  )
}

const titleStyle = {
  margin: '0 0 12px',
  color: 'var(--text-1)',
  fontSize: 'var(--font-size-page-title)',
  lineHeight: 1.3,
} as const

const textStyle = {
  margin: 0,
  color: 'var(--text-2)',
} as const

export default SensorHealthPage
