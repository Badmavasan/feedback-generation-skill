import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Platforms from './pages/Platforms'
import Generate from './pages/Generate'
import FeedbackHistory from './pages/FeedbackHistory'
import FeedbackTrace from './pages/FeedbackTrace'
import Layout from './components/Layout'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('token')
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/*"
          element={
            <RequireAuth>
              <Layout>
                <Routes>
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/platforms" element={<Platforms />} />
                  <Route path="/generate" element={<Generate />} />
                  <Route path="/history" element={<FeedbackHistory />} />
                  <Route path="/history/:id" element={<FeedbackTrace />} />
                  <Route path="*" element={<Navigate to="/dashboard" replace />} />
                </Routes>
              </Layout>
            </RequireAuth>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
