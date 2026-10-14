/**
 * Iter 158 — LeagueAdminTab extracted from CommissionerSettings.tsx.
 *
 * Wraps the inner Teams / Schedules / Season Awards sub-tabs that sit
 * inside the parent "League Administration" tab. Parent owns the active
 * sub-tab state so it survives across parent tab changes.
 */
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Users, Calendar, Trophy } from "lucide-react";
import TeamsTab from "@/lovable/components/admin/TeamsTab";
import SchedulesTab from "@/lovable/components/admin/SchedulesTab";
import { SeasonAwardsTab } from "@/lovable/components/admin/SeasonAwardsTab";

interface LeagueAdminTabProps {
  adminSubTab: string;
  setAdminSubTab: (v: string) => void;
  isH2H: boolean;
  league: any;
}

export default function LeagueAdminTab({ adminSubTab, setAdminSubTab, isH2H, league }: LeagueAdminTabProps) {
  return (
    <Tabs value={adminSubTab} onValueChange={setAdminSubTab} data-testid="commissioner-league-admin-tab">
      <TabsList className="bg-secondary border border-border flex flex-wrap h-auto justify-start">
        <TabsTrigger value="teams" className="data-[state=active]:bg-primary/20" data-testid="admin-sub-tab-team-owner-list">
          <Users className="h-4 w-4 mr-2" />
          {/* Iter 231ar — Renamed from "Teams" so the label matches
              what the tab actually shows: the team + owner + email
              roster (vs. SchedulesTab / SeasonAwardsTab siblings). */}
          Team and Owner List
        </TabsTrigger>
        <TabsTrigger value="schedules" className="data-[state=active]:bg-primary/20">
          <Calendar className="h-4 w-4 mr-2" />
          Schedules
        </TabsTrigger>
        <TabsTrigger
          value="season-awards"
          className="data-[state=active]:bg-primary/20"
          data-testid="admin-tab-season-awards"
        >
          <Trophy className="h-4 w-4 mr-2" />
          Season Awards
        </TabsTrigger>
      </TabsList>
      <TabsContent value="teams">
        <TeamsTab />
      </TabsContent>
      <TabsContent value="schedules">
        {!isH2H ? (
          <Card className="bg-card border-border opacity-50">
            <CardContent className="py-12 text-center space-y-2">
              <Calendar className="h-8 w-8 text-muted-foreground mx-auto" />
              <p className="text-sm font-medium text-muted-foreground">
                Matchup scheduling is only available for Head-to-Head formats
              </p>
              <p className="text-xs text-muted-foreground">
                Switch to a Head-to-Head scoring format in League Setup to configure schedules
              </p>
            </CardContent>
          </Card>
        ) : (
          <SchedulesTab league={league} />
        )}
      </TabsContent>
      <TabsContent value="season-awards">
        <SeasonAwardsTab />
      </TabsContent>
    </Tabs>
  );
}
