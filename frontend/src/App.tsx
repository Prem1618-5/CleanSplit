import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import GroupDetail from './pages/GroupDetail';
import ImportPage from './pages/ImportPage';
import ImportReview from './pages/ImportReview';
import Balances from './pages/Balances';

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="spinner" />;
  return user ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={
            <PrivateRoute><Layout /></PrivateRoute>
          }>
            <Route index element={<Dashboard />} />
            <Route path="groups/:id" element={<GroupDetail />} />
            <Route path="groups/:id/balances" element={<Balances />} />
            <Route path="groups/:id/import" element={<ImportPage />} />
            <Route path="import/:sessionId/review" element={<ImportReview />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
