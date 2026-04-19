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
import DraftRoomPage from "@/pages/DraftRoomPage";
import AuctionDraftPage from "@/pages/AuctionDraftPage";
import ScoringPage from "@/pages/ScoringPage";
import TradeBlockPage from "@/pages/TradeBlockPage";
import TransactionsPage from "@/pages/TransactionsPage";
import WaiversPage from "@/pages/WaiversPage";
import RosterPage from "@/pages/RosterPage";
import StandingsPage from "@/pages/StandingsPage";
import CommissionerPage from "@/pages/CommissionerPage";
import PlayerDetailPage from "@/pages/PlayerDetailPage";
import SalaryCapPage from "@/pages/SalaryCapPage";
import ActivityFeedPage from "@/pages/ActivityFeedPage";

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
          <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
          <Route path="/leagues" element={<ProtectedRoute><LeaguesPage /></ProtectedRoute>} />
          <Route path="/leagues/create" element={<ProtectedRoute><CreateLeaguePage /></ProtectedRoute>} />
          <Route path="/leagues/:id" element={<ProtectedRoute><LeagueDetailPage /></ProtectedRoute>} />
          <Route path="/players" element={<ProtectedRoute><PlayersPage /></ProtectedRoute>} />
          <Route path="/drafts" element={<ProtectedRoute><DraftsPage /></ProtectedRoute>} />
          <Route path="/draft-room" element={<ProtectedRoute><DraftRoomPage /></ProtectedRoute>} />
          <Route path="/draft-room/:id" element={<ProtectedRoute><DraftRoomPage /></ProtectedRoute>} />
          <Route path="/auction-draft/:id" element={<ProtectedRoute><AuctionDraftPage /></ProtectedRoute>} />
          <Route path="/trade-block" element={<ProtectedRoute><TradeBlockPage /></ProtectedRoute>} />
          <Route path="/transactions" element={<ProtectedRoute><TransactionsPage /></ProtectedRoute>} />
          <Route path="/waivers" element={<ProtectedRoute><WaiversPage /></ProtectedRoute>} />
          <Route path="/roster" element={<ProtectedRoute><RosterPage /></ProtectedRoute>} />
          <Route path="/scoring" element={<ProtectedRoute><ScoringPage /></ProtectedRoute>} />
          <Route path="/commissioner" element={<ProtectedRoute><CommissionerPage /></ProtectedRoute>} />
          <Route path="/players/:id" element={<ProtectedRoute><PlayerDetailPage /></ProtectedRoute>} />
          <Route path="/salary-cap" element={<ProtectedRoute><SalaryCapPage /></ProtectedRoute>} />
          <Route path="/activity" element={<ProtectedRoute><ActivityFeedPage /></ProtectedRoute>} />
          <Route path="/standings" element={<ProtectedRoute><StandingsPage /></ProtectedRoute>} />
          <Route path="/analytics" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
          <Route path="/draft-board" element={<ProtectedRoute><DraftsPage /></ProtectedRoute>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
