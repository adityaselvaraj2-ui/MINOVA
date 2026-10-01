import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import ShiftEntryPage from "./pages/ShiftEntryPage";
import ApprovalQueuePage from "./pages/ApprovalQueuePage";
import ReportsPage from "./pages/ReportsPage";
import ReportDetailPage from "./pages/ReportDetailPage";
import DocumentsPage from "./pages/DocumentsPage";
import ReviewPage from "./pages/ReviewPage";
import TopicsPage from "./pages/TopicsPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import PlanningPage from "./pages/PlanningPage";
import HealthPage from "./pages/HealthPage";
import "./App.css";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
      />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="shift-entry" element={<ShiftEntryPage />} />
        <Route path="approvals" element={<ApprovalQueuePage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="reports/:id" element={<ReportDetailPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="review" element={<ReviewPage />} />
        <Route path="topics" element={<TopicsPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="planning" element={<PlanningPage />} />
        <Route path="health" element={<HealthPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
