// @ts-nocheck
import { AppLayout } from "@/components/layout/AppLayout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TrendingUp, TrendingDown, Clock, Zap } from "lucide-react";

interface Prospect {
  id: number;
  name: string;
  position: string;
  team: string;
  age: number;
  league: string;
  eta: string;
  grade: "A" | "B" | "C" | "D";
  
  trend: "up" | "down" | "stable";
  stats: string;
  owner?: string;
}

const prospects: Prospect[] = [
  { id: 1, name: "Connor Bedard", position: "C", team: "CHI", age: 18, league: "NHL", eta: "Now", grade: "A", trend: "up", stats: "22G, 38A in 52GP", owner: "Glacier Kings" },
  { id: 2, name: "Macklin Celebrini", position: "C", team: "SJS", age: 17, league: "NCAA", eta: "2024", grade: "A", trend: "up", stats: "32G, 32A in 38GP" },
  { id: 3, name: "Matvei Michkov", position: "RW", team: "PHI", age: 19, league: "KHL", eta: "2025", grade: "A", trend: "stable", stats: "18G, 25A in 47GP" },
  { id: 4, name: "Logan Stankoven", position: "C", team: "DAL", age: 20, league: "AHL", eta: "2024", grade: "B", trend: "up", stats: "24G, 28A in 45GP", owner: "Ice Crushers" },
  { id: 5, name: "Lane Hutson", position: "D", team: "MTL", age: 19, league: "NCAA", eta: "2024", grade: "B", trend: "up", stats: "8G, 42A in 38GP" },
  { id: 6, name: "Cutter Gauthier", position: "LW", team: "ANA", age: 20, league: "NCAA", eta: "2024", grade: "B", trend: "stable", stats: "21G, 18A in 35GP" },
  { id: 7, name: "Oliver Moore", position: "C", team: "CBJ", age: 18, league: "USNTDP", eta: "2026", grade: "B", trend: "up", stats: "19G, 25A in 42GP" },
  { id: 8, name: "Will Smith", position: "C", team: "SJS", age: 18, league: "NCAA", eta: "2025", grade: "B", trend: "stable", stats: "25G, 43A in 40GP", owner: "Team Frostbite" },
];

const myProspects = prospects.filter(p => p.owner === "Team Frostbite");

const Prospects = () => {
  return (
    <AppLayout>
      <div className="container py-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Prospect Rankings</h1>
            <p className="text-muted-foreground">Minor league and draft-eligible prospect tracker</p>
          </div>
        </div>

        <Tabs defaultValue="rankings" className="space-y-4">
          <TabsList className="bg-secondary">
            <TabsTrigger value="rankings">Top Prospects</TabsTrigger>
            <TabsTrigger value="my-prospects">My Prospects</TabsTrigger>
            <TabsTrigger value="available">Available</TabsTrigger>
          </TabsList>

          <TabsContent value="rankings">
            <div className="grid gap-4">
              {prospects.map((prospect, index) => (
                <ProspectCard key={prospect.id} prospect={prospect} rank={index + 1} />
              ))}
            </div>
          </TabsContent>

          <TabsContent value="my-prospects">
            {myProspects.length > 0 ? (
              <div className="grid gap-4">
                {myProspects.map((prospect, index) => (
                  <ProspectCard key={prospect.id} prospect={prospect} rank={prospects.indexOf(prospect) + 1} />
                ))}
              </div>
            ) : (
              <Card className="bg-card border-border">
                <CardContent className="py-12 text-center text-muted-foreground">
                  You don't have any prospects on your roster
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="available">
            <div className="grid gap-4">
              {prospects.filter(p => !p.owner).map((prospect, index) => (
                <ProspectCard key={prospect.id} prospect={prospect} rank={prospects.indexOf(prospect) + 1} available />
              ))}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
};

const ProspectCard = ({ prospect, rank, available }: { prospect: Prospect; rank: number; available?: boolean }) => {
  const getGradeColor = (grade: string) => {
    switch (grade) {
      case "A": return "bg-success/20 text-success border-success/30";
      case "B": return "bg-primary/20 text-primary border-primary/30";
      case "C": return "bg-accent/20 text-accent border-accent/30";
      case "D": return "bg-muted text-muted-foreground border-border";
      default: return "";
    }
  };

  return (
    <Card className={`bg-card border-border hover:border-primary/30 transition-colors ${available ? "border-l-4 border-l-success" : ""}`}>
      <CardContent className="p-5">
        <div className="flex items-start gap-4">
          <div className="flex items-center gap-3">
            <div className={`h-10 w-10 rounded-lg flex items-center justify-center font-display text-xl ${rank <= 3 ? "bg-accent/20 text-accent" : "bg-secondary text-muted-foreground"}`}>
              {rank}
            </div>
            <div className="h-14 w-14 rounded-lg bg-gradient-to-br from-secondary to-muted flex items-center justify-center text-sm font-bold">
              {prospect.team}
            </div>
          </div>

          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-semibold text-lg">{prospect.name}</h3>
              {prospect.trend === "up" && <TrendingUp className="h-4 w-4 text-success" />}
              {prospect.trend === "down" && <TrendingDown className="h-4 w-4 text-destructive" />}
              <Badge className={getGradeColor(prospect.grade)}>
                Grade {prospect.grade}
              </Badge>
            </div>

            <div className="flex items-center gap-3 text-sm text-muted-foreground mb-2">
              <span>{prospect.position}</span>
              <span>•</span>
              <span>{prospect.team}</span>
              <span>•</span>
              <span>Age {prospect.age}</span>
              <span>•</span>
              <span>{prospect.league}</span>
            </div>

            <div className="flex items-center gap-4 text-sm">
              <div className="flex items-center gap-1">
                <Clock className="h-4 w-4 text-accent" />
                <span className="text-muted-foreground">ETA:</span>
                <span className="font-medium text-accent">{prospect.eta}</span>
              </div>
              <div className="flex items-center gap-1">
                <Zap className="h-4 w-4 text-primary" />
                <span className="text-muted-foreground">Stats:</span>
                <span className="font-medium">{prospect.stats}</span>
              </div>
            </div>
          </div>

          <div className="text-right">
            {prospect.owner && (
              <Badge variant="outline" className="mt-2 text-xs">
                {prospect.owner}
              </Badge>
            )}
            {available && (
              <Badge className="mt-2 bg-success/20 text-success border-success/30 text-xs">
                Available
              </Badge>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default Prospects;
