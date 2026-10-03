import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Trophy, Save } from "lucide-react";
import api, { formatApiError } from "@/lib/api";

const DEFAULT_SKATER_SCORING = {
  goals: 3, assists: 2, plus_minus: 1, penalty_minutes: -0.5,
  power_play_goals: 1, power_play_points: 0.5,
  short_handed_goals: 2, short_handed_points: 1,
  game_winning_goals: 1, shots: 0.5, faceoff_wins: 0.1,
};

const DEFAULT_GOALIE_SCORING = {
  wins: 5, losses: -2, saves: 0.2, goals_against: -1,
  shutouts: 3, overtime_losses: 0,
};

const ROTO_CATEGORIES = [
  "goals", "assists", "plus_minus", "power_play_points",
  "shots", "penalty_minutes", "wins", "save_pct", "goals_against_avg", "shutouts",
];

const SCORING_LABELS = {
  goals: "Goals", assists: "Assists", plus_minus: "+/-",
  penalty_minutes: "PIM", power_play_goals: "PPG",
  power_play_points: "PPP", short_handed_goals: "SHG",
  short_handed_points: "SHP", game_winning_goals: "GWG",
  shots: "Shots", faceoff_wins: "FOW",
  wins: "Wins", losses: "Losses", saves: "Saves",
  goals_against: "Goals Against", shutouts: "Shutouts",
  overtime_losses: "OT Losses", save_pct: "Save %",
  goals_against_avg: "GAA",
};

export default function ScoringPage() {
  const [leagueId, setLeagueId] = useState(null);
  const [skaterScoring, setSkaterScoring] = useState(DEFAULT_SKATER_SCORING);
  const [goalieScoring, setGoalieScoring] = useState(DEFAULT_GOALIE_SCORING);
  const [rotoCategories, setRotoCategories] = useState(ROTO_CATEGORIES);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const init = async () => {
      try {
        const { data: leagues } = await api.get("/leagues?my_leagues=true");
        if (leagues.length > 0) {
          setLeagueId(leagues[0].id);
          // Load existing scoring config
          try {
            const { data } = await api.get(`/scoring/config?league_id=${leagues[0].id}`);
            if (data.skater_scoring) setSkaterScoring(data.skater_scoring);
            if (data.goalie_scoring) setGoalieScoring(data.goalie_scoring);
            if (data.roto_categories) setRotoCategories(data.roto_categories);
          } catch (e) { /* Use defaults */ }
        }
      } catch (e) { console.error(e); }
    };
    init();
  }, []);

  const handleSave = async () => {
    if (!leagueId) return;
    setSaving(true);
    try {
      await api.post("/scoring/config", {
        league_id: leagueId,
        skater_scoring: skaterScoring,
        goalie_scoring: goalieScoring,
        roto_categories: rotoCategories,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) { alert(formatApiError(e)); }
    setSaving(false);
  };

  const toggleRotoCategory = (cat) => {
    setRotoCategories(prev =>
      prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
    );
  };

  return (
    <AppLayout>
      <div className="space-y-6" data-testid="scoring-page">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Trophy className="h-6 w-6 text-[#00D2FF]" />
              Scoring Settings
            </h1>
            <p className="text-[#A1A1AA]">Configure fantasy point values and rotisserie categories</p>
          </div>
          <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]" onClick={handleSave} disabled={saving} data-testid="save-scoring">
            <Save className="h-4 w-4 mr-2" />
            {saving ? "Saving..." : saved ? "Saved!" : "Save Settings"}
          </Button>
        </div>

        <Tabs defaultValue="points">
          <TabsList>
            <TabsTrigger value="points">Points-Based Scoring</TabsTrigger>
            <TabsTrigger value="roto">Rotisserie Categories</TabsTrigger>
          </TabsList>

          <TabsContent value="points" className="space-y-6 mt-4">
            {/* Skater Scoring */}
            <Card className="border-white/10">
              <CardHeader>
                <CardTitle className="text-white">Skater Scoring</CardTitle>
                <CardDescription className="text-[#A1A1AA]">Set point values for skater statistics</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                  {Object.entries(skaterScoring).map(([key, value]) => (
                    <div key={key}>
                      <Label className="text-[#A1A1AA] text-xs">{SCORING_LABELS[key] || key}</Label>
                      <Input
                        type="number"
                        step="0.1"
                        value={value}
                        onChange={e => setSkaterScoring(prev => ({ ...prev, [key]: parseFloat(e.target.value) || 0 }))}
                        className="mt-1 bg-[#0A0A0A] border-white/10 text-white"
                        data-testid={`skater-${key}`}
                      />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Goalie Scoring */}
            <Card className="border-white/10">
              <CardHeader>
                <CardTitle className="text-white">Goalie Scoring</CardTitle>
                <CardDescription className="text-[#A1A1AA]">Set point values for goalie statistics</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  {Object.entries(goalieScoring).map(([key, value]) => (
                    <div key={key}>
                      <Label className="text-[#A1A1AA] text-xs">{SCORING_LABELS[key] || key}</Label>
                      <Input
                        type="number"
                        step="0.1"
                        value={value}
                        onChange={e => setGoalieScoring(prev => ({ ...prev, [key]: parseFloat(e.target.value) || 0 }))}
                        className="mt-1 bg-[#0A0A0A] border-white/10 text-white"
                        data-testid={`goalie-${key}`}
                      />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="roto" className="mt-4">
            <Card className="border-white/10">
              <CardHeader>
                <CardTitle className="text-white">Rotisserie Categories</CardTitle>
                <CardDescription className="text-[#A1A1AA]">Select which statistical categories to rank teams in</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-3">
                  {Object.keys(SCORING_LABELS).map(cat => (
                    <button
                      key={cat}
                      onClick={() => toggleRotoCategory(cat)}
                      className={`px-4 py-2 rounded-lg border transition-colors ${
                        rotoCategories.includes(cat)
                          ? "bg-[#00D2FF]/20 border-[#00D2FF] text-[#00D2FF]"
                          : "border-white/10 text-[#A1A1AA] hover:border-white/20"
                      }`}
                      data-testid={`roto-${cat}`}
                    >
                      {SCORING_LABELS[cat]}
                    </button>
                  ))}
                </div>
                <p className="text-sm text-[#A1A1AA] mt-4">{rotoCategories.length} categories selected</p>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
}
