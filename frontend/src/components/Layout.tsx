import { Activity, List, Map as MapIcon, TrendingUp } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

const navigationItems = [
  { label: 'Map', path: '/', Icon: MapIcon, end: true },
  { label: 'Inventory', path: '/inventory', Icon: List, end: false },
  { label: 'Forecast', path: '/forecast', Icon: TrendingUp, end: false },
  { label: 'Sensor health', path: '/sensors', Icon: Activity, end: false },
]

function Layout() {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        color: 'var(--text-1)',
        background: 'var(--surface-0)',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <header
        style={{
          height: 60,
          display: 'flex',
          alignItems: 'center',
          padding: '0 24px',
          borderBottom: '1px solid var(--border)',
          background: 'var(--surface-1)',
        }}
      >
        <span style={{ color: 'var(--accent)', fontSize: 20, fontWeight: 600 }}>
          FloorTrack AI
        </span>
      </header>

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <aside
          style={{
            width: 220,
            flex: '0 0 220px',
            padding: '20px 12px',
            borderRight: '1px solid var(--border)',
            background: 'var(--surface-1)',
          }}
        >
          <nav
            aria-label="Main navigation"
            style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
          >
            {navigationItems.map(({ label, path, Icon, end }) => (
              <NavLink
                key={path}
                to={path}
                end={end}
                style={({ isActive }) => ({
                  minHeight: 44,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: '0 12px',
                  borderRadius: 6,
                  color: isActive ? 'var(--accent)' : 'var(--text-2)',
                  background: isActive ? 'var(--accent-subtle)' : 'transparent',
                  fontSize: 14,
                  fontWeight: isActive ? 600 : 500,
                  textDecoration: 'none',
                })}
              >
                <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>
        </aside>

        <main style={{ minWidth: 0, flex: 1, padding: 24 }}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default Layout
