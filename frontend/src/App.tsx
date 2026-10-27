import { Navigate, Route, Routes } from 'react-router-dom'
import './styles/global.css'
import './styles/tokens.css'
import Layout from './components/Layout'
import ForecastPage from './pages/ForecastPage'
import InventoryPage from './pages/InventoryPage'
import MapPage from './pages/MapPage'
import SensorHealthPage from './pages/SensorHealthPage'

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<MapPage />} />
        <Route path="inventory" element={<InventoryPage />} />
        <Route path="forecast" element={<ForecastPage />} />
        <Route path="sensors" element={<SensorHealthPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default App
