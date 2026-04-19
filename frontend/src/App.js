import "@/App.css";
import "@/index.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import ProtectedRoute from "@/components/layout/ProtectedRoute";

// Pages
import LandingPage from "@/pages/LandingPage";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import DashboardPage from "@/pages/DashboardPage";
import LeaguesPage from "@/pages/LeaguesPage";
import CreateLeaguePage from "@/pages/CreateLeaguePage";
import LeagueDetailPage from "@/pages/LeagueDetailPage";
import PlayersPage from "@/pages/PlayersPage";
import DraftsPage from "@/pages/DraftsPage";

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Routes */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          
          {/* Protected Routes */}
          <Route path="/dashboard" element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          } />
          <Route path="/leagues" element={
            <ProtectedRoute>
              <LeaguesPage />
            </ProtectedRoute>
          } />
          <Route path="/leagues/create" element={
            <ProtectedRoute>
              <CreateLeaguePage />
            </ProtectedRoute>
          } />
          <Route path="/leagues/:id" element={
            <ProtectedRoute>
              <LeagueDetailPage />
            </ProtectedRoute>
          } />
          <Route path="/players" element={
            <ProtectedRoute>
              <PlayersPage />
            </ProtectedRoute>
          } />
          <Route path="/drafts" element={
            <ProtectedRoute>
              <DraftsPage />
            </ProtectedRoute>
          } />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
