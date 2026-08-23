import { Suspense, lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { LoadingState } from './components/StatusStates'

const ExecutiveOverviewPage = lazy(() =>
  import('./pages/ExecutiveOverviewPage').then((m) => ({ default: m.ExecutiveOverviewPage })),
)
const CountryProfilePage = lazy(() =>
  import('./pages/CountryProfilePage').then((m) => ({ default: m.CountryProfilePage })),
)
const EnergyTransitionPage = lazy(() =>
  import('./pages/EnergyTransitionPage').then((m) => ({ default: m.EnergyTransitionPage })),
)
const ScenarioExplorerPage = lazy(() =>
  import('./pages/ScenarioExplorerPage').then((m) => ({ default: m.ScenarioExplorerPage })),
)
const ModelEvidencePage = lazy(() =>
  import('./pages/ModelEvidencePage').then((m) => ({ default: m.ModelEvidencePage })),
)
const StructuralDiagnosticsPage = lazy(() =>
  import('./pages/StructuralDiagnosticsPage').then((m) => ({ default: m.StructuralDiagnosticsPage })),
)
const ProvenancePage = lazy(() =>
  import('./pages/ProvenancePage').then((m) => ({ default: m.ProvenancePage })),
)
const NotFoundPage = lazy(() =>
  import('./pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
)

export default function App() {
  return (
    <Suspense fallback={<LoadingState label="Loading page…" />}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<ExecutiveOverviewPage />} />
          <Route path="country/:iso3" element={<CountryProfilePage />} />
          <Route path="energy" element={<EnergyTransitionPage />} />
          <Route path="scenarios" element={<ScenarioExplorerPage />} />
          <Route path="evidence" element={<ModelEvidencePage />} />
          <Route path="diagnostics" element={<StructuralDiagnosticsPage />} />
          <Route path="provenance" element={<ProvenancePage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
