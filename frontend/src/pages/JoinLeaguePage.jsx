import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Trophy, Users, CheckCircle2 } from "lucide-react";

export default function JoinLeaguePage() {
  const { code } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [teamName, setTeamName] = useState("");
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(null);

  const handleJoin = async () => {
    if (!teamName.trim()) return;
    setJoining(true);
    setError("");
    try {
      const { data } = await api.post("/leagues/join-by-invite", {
        invite_code: code,
        team_name: teamName.trim()
      });
      setSuccess(data);
    } catch (e) {
      setError(formatApiError(e));
    }
    setJoining(false);
  };

  if (!user) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center p-6">
        <Card className="border-white/10 max-w-md w-full">
          <CardContent className="p-8 text-center">
            <Trophy className="h-16 w-16 text-[#00D2FF] mx-auto mb-4" />
            <h1 className="font-heading text-2xl font-bold text-white mb-2">You've Been Invited!</h1>
            <p className="text-[#A1A1AA] mb-6">Sign in or create an account to join the league</p>
            <Button className="w-full bg-[#00D2FF] text-black mb-3" onClick={() => navigate(`/login?redirect=/join/${code}`)}>Sign In</Button>
            <Button variant="outline" className="w-full border-white/10 text-white" onClick={() => navigate(`/register?redirect=/join/${code}`)}>Create Account</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center p-6">
        <Card className="border-white/10 max-w-md w-full">
          <CardContent className="p-8 text-center">
            <CheckCircle2 className="h-16 w-16 text-[#34C759] mx-auto mb-4" />
            <h1 className="text-2xl font-bold text-white mb-2">Welcome to {success.league_name}!</h1>
            <p className="text-[#A1A1AA] mb-6">Your team has been created</p>
            <Button className="w-full bg-[#00D2FF] text-black" onClick={() => navigate(`/leagues/${success.league_id}`)} data-testid="go-to-league">Go to League</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center p-6" data-testid="join-league-page">
      <Card className="border-white/10 max-w-md w-full">
        <CardContent className="p-8">
          <div className="text-center mb-8">
            <Users className="h-12 w-12 text-[#00D2FF] mx-auto mb-3" />
            <h1 className="text-2xl font-bold text-white mb-1">Join League</h1>
            <p className="text-[#A1A1AA]">Invite code: <span className="font-mono text-[#00D2FF]">{code}</span></p>
          </div>
          {error && <div className="bg-[#FF3B30]/20 text-[#FF3B30] p-3 rounded mb-4 text-sm">{error}</div>}
          <div className="space-y-4">
            <div>
              <label className="text-sm text-[#A1A1AA]">Team Name</label>
              <Input value={teamName} onChange={e => setTeamName(e.target.value)} placeholder="Enter your team name" className="mt-2 bg-[#141414] border-white/10 text-white" data-testid="join-team-name" />
            </div>
            <Button className="w-full bg-[#00D2FF] text-black hover:bg-[#33DBFF]" onClick={handleJoin} disabled={joining || !teamName.trim()} data-testid="join-submit">
              {joining ? "Joining..." : "Join League"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
