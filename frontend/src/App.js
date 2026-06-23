import "@/App.css";
import "@/index.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import ImpersonationBanner from "@/components/ImpersonationBanner";
import { usePageviewTracker } from "@/hooks/use-pageview-tracker";
import { TradeBuilderProvider } from "@/lovable/state/TradeBuilderContext";
import ProtectedRoute from "@/components/layout/ProtectedRoute";

// Landing / auth (keep existing)
import LandingPage from "@/pages/LandingPage";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import JoinLeaguePage from "@/pages/JoinLeaguePage";
import PaymentSuccessPage from "@/pages/PaymentSuccessPage";
import PaymentCancelPage from "@/pages/PaymentCancelPage";
import ProfilePage from "@/pages/ProfilePage";
import EditProfilePage from "@/pages/EditProfilePage";
import ForumPage from "@/pages/ForumPage";

// Backend-wired pages (our existing, data-driven)
import DashboardPage from "@/pages/DashboardPage";
import LeaguesPage from "@/pages/LeaguesPage";
import CreateLeaguePage from "@/pages/CreateLeaguePage";
import LeagueDetailPage from "@/pages/LeagueDetailPage";
import PlayersPage from "@/pages/PlayersPage";
import DraftsPage from "@/pages/DraftsPage";
import DraftRoomPage from "@/pages/DraftRoomPage";
import AuctionDraftPage from "@/pages/AuctionDraftPage";
import CommissionerPage from "@/pages/CommissionerPage";
import PlayerDetailPage from "@/pages/PlayerDetailPage";
import ComparePage from "@/pages/ComparePage";
import TradeAnalyzerPage from "@/pages/TradeAnalyzerPage";
import LiveScoringPage from "@/pages/LiveScoringPage";
import TeamDetailPage from "@/pages/TeamDetailPage";

// Lovable-ported pages (design migration)
import LovableIndex from "@/lovable/pages/Index";
import LovableTeam from "@/lovable/pages/Team";
import LovableMatchup from "@/lovable/pages/Matchup";
import LovableStandings from "@/lovable/pages/Standings";
import LovableTransactions from "@/lovable/pages/Transactions";
import LovableWaivers from "@/lovable/pages/Waivers";
import LovableTradeBlock from "@/lovable/pages/TradeBlock";
import LovableDepthChart from "@/lovable/pages/DepthChart";
import LovableSalaryCap from "@/lovable/pages/SalaryCap";
import LovableScoring from "@/lovable/pages/Scoring";
import LovableDraftBoard from "@/lovable/pages/DraftBoard";
import LovableDraftRoom from "@/lovable/pages/DraftRoom";
// Iter 203 — Draft History
import LovableDraftHistory from "@/lovable/pages/DraftHistory";
import LovableDraftLottery from "@/lovable/pages/DraftLottery";
import LovableLeagueHistory from "@/lovable/pages/LeagueHistory";
import LovableTrophyRoom from "@/lovable/pages/TrophyRoom";
import LovableFranchiseRecords from "@/lovable/pages/FranchiseRecords";
import LovableAnalytics from "@/lovable/pages/Analytics";
import LovableChat from "@/lovable/pages/Chat";
import LovableCommissionerSettings from "@/lovable/pages/CommissionerSettings";
// Iter 187 — Commissioner Ops Console
import OpsConsolePage from "@/lovable/pages/commissioner/OpsConsole";
import AdminDashboard from "@/lovable/pages/admin/AdminDashboard";
// Iter 193 — Bulk Owner Invites
import OwnerInvitesPage from "@/lovable/pages/commissioner/OwnerInvites";
import LovableLeaguePayments from "@/lovable/pages/LeaguePayments";
import LovablePlayerNews from "@/lovable/pages/PlayerNews";
import LovablePlayerPool from "@/lovable/pages/PlayerPool";
import LovableProspects from "@/lovable/pages/Prospects";
import LovableSiteAdmin from "@/lovable/pages/SiteAdmin";
import LovableTeamsOwners from "@/lovable/pages/TeamsOwners";
import LovableNotFound from "@/lovable/pages/NotFound";
import LovableLeagueSearch from "@/lovable/pages/LeagueSearch";
import { Toaster } from "@/components/ui/sonner";

function PageviewTrackerMount() {
  usePageviewTracker();
  return null;
}

function App() {
  return (
    <AuthProvider>
      <Toaster position="top-right" richColors closeButton />
      <BrowserRouter>
        <ImpersonationBanner />
        <PageviewTrackerMount />
        <TradeBuilderProvider>
        <Routes>
          {/* Public */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/join/:code" element={<JoinLeaguePage />} />
          <Route path="/u/:username" element={<ProfilePage />} />
          <Route path="/profile/edit" element={<ProtectedRoute><EditProfilePage /></ProtectedRoute>} />
          <Route path="/forum" element={<ProtectedRoute><ForumPage /></ProtectedRoute>} />

          {/* Backend-wired (data-driven) */}
          <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
          <Route path="/leagues" element={<ProtectedRoute><LeaguesPage /></ProtectedRoute>} />
          <Route path="/league-search" element={<ProtectedRoute><LovableLeagueSearch /></ProtectedRoute>} />
          <Route path="/leagues/create" element={<ProtectedRoute><CreateLeaguePage /></ProtectedRoute>} />
          <Route path="/leagues/:id" element={<ProtectedRoute><LeagueDetailPage /></ProtectedRoute>} />
          <Route path="/players" element={<ProtectedRoute><PlayersPage /></ProtectedRoute>} />
          <Route path="/players/:id" element={<ProtectedRoute><PlayerDetailPage /></ProtectedRoute>} />
          <Route path="/compare" element={<ProtectedRoute><ComparePage /></ProtectedRoute>} />
          <Route path="/trade-analyzer" element={<ProtectedRoute><TradeAnalyzerPage /></ProtectedRoute>} />
          <Route path="/drafts" element={<ProtectedRoute><DraftsPage /></ProtectedRoute>} />
          <Route path="/draft-room/:id" element={<ProtectedRoute><DraftRoomPage /></ProtectedRoute>} />
          <Route path="/auction-draft/:id" element={<ProtectedRoute><AuctionDraftPage /></ProtectedRoute>} />
          <Route path="/commissioner" element={<ProtectedRoute><CommissionerPage /></ProtectedRoute>} />
          <Route path="/live" element={<ProtectedRoute><LiveScoringPage /></ProtectedRoute>} />
          <Route path="/teams/:id" element={<ProtectedRoute><TeamDetailPage /></ProtectedRoute>} />
          <Route path="/payment/success" element={<ProtectedRoute><PaymentSuccessPage /></ProtectedRoute>} />
          <Route path="/payment/cancel" element={<ProtectedRoute><PaymentCancelPage /></ProtectedRoute>} />

          {/* Lovable-ported design pages */}
          <Route path="/league/:leagueId/home" element={<ProtectedRoute><LovableIndex /></ProtectedRoute>} />
          <Route path="/roster" element={<ProtectedRoute><LovableTeam /></ProtectedRoute>} />
          <Route path="/team" element={<ProtectedRoute><LovableTeam /></ProtectedRoute>} />
          <Route path="/matchup" element={<ProtectedRoute><LovableMatchup /></ProtectedRoute>} />
          <Route path="/standings" element={<ProtectedRoute><LovableStandings /></ProtectedRoute>} />
          <Route path="/transactions" element={<ProtectedRoute><LovableTransactions /></ProtectedRoute>} />
          <Route path="/waivers" element={<ProtectedRoute><LovableWaivers /></ProtectedRoute>} />
          <Route path="/trade-block" element={<ProtectedRoute><LovableTradeBlock /></ProtectedRoute>} />
          <Route path="/depth-chart" element={<ProtectedRoute><LovableDepthChart /></ProtectedRoute>} />
          <Route path="/salary-cap" element={<ProtectedRoute><LovableSalaryCap /></ProtectedRoute>} />
          <Route path="/scoring" element={<ProtectedRoute><LovableScoring /></ProtectedRoute>} />
          <Route path="/league-info" element={<ProtectedRoute><LovableScoring /></ProtectedRoute>} />
          <Route path="/draft-board" element={<ProtectedRoute><LovableDraftBoard /></ProtectedRoute>} />
          <Route path="/draft-room" element={<ProtectedRoute><LovableDraftRoom /></ProtectedRoute>} />
          <Route path="/draft-history" element={<ProtectedRoute><LovableDraftHistory /></ProtectedRoute>} />
          <Route path="/draft-lottery" element={<ProtectedRoute><LovableDraftLottery /></ProtectedRoute>} />
          <Route path="/league-history" element={<ProtectedRoute><LovableLeagueHistory /></ProtectedRoute>} />
          <Route path="/trophy-room" element={<ProtectedRoute><LovableTrophyRoom /></ProtectedRoute>} />
          <Route path="/trophy-room/team/:teamId" element={<ProtectedRoute><LovableTrophyRoom /></ProtectedRoute>} />
          <Route path="/franchise-records" element={<ProtectedRoute><LovableFranchiseRecords /></ProtectedRoute>} />
          <Route path="/analytics" element={<ProtectedRoute><LovableAnalytics /></ProtectedRoute>} />
          <Route path="/chat" element={<ProtectedRoute><LovableChat /></ProtectedRoute>} />
          <Route path="/commissioner/settings" element={<ProtectedRoute><LovableCommissionerSettings /></ProtectedRoute>} />
          {/* Iter 187 — Commissioner Ops Console */}
          <Route path="/commissioner/ops-console" element={<ProtectedRoute><OpsConsolePage /></ProtectedRoute>} />
          {/* Iter 193 — Bulk Owner Invites */}
          <Route path="/commissioner/owner-invites" element={<ProtectedRoute><OwnerInvitesPage /></ProtectedRoute>} />
          <Route path="/league-payments" element={<ProtectedRoute><LovableLeaguePayments /></ProtectedRoute>} />
          <Route path="/player-news" element={<ProtectedRoute><LovablePlayerNews /></ProtectedRoute>} />
          <Route path="/player-pool" element={<ProtectedRoute><LovablePlayerPool /></ProtectedRoute>} />
          <Route path="/prospects" element={<ProtectedRoute><LovableProspects /></ProtectedRoute>} />
          <Route path="/site-admin" element={<ProtectedRoute><LovableSiteAdmin /></ProtectedRoute>} />
          {/* Iter 201a — Platform admin dashboard (admin role gate is enforced inside the component) */}
          <Route path="/admin" element={<ProtectedRoute><AdminDashboard /></ProtectedRoute>} />
          <Route path="/teams-owners" element={<ProtectedRoute><LovableTeamsOwners /></ProtectedRoute>} />

          {/* 404 */}
          <Route path="*" element={<LovableNotFound />} />
        </Routes>
        </TradeBuilderProvider>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
