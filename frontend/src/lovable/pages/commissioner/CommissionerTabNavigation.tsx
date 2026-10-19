import { TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Users, Trophy, Shield, Target, LayoutGrid, AlertTriangle, ClipboardCheck, ScrollText, UserCog, Sliders, DollarSign } from "lucide-react";

// Iter 231an — Single source of truth for the Commissioner Settings
// tab strip. Used by both the desktop `TabsList` and the mobile
// `<Select>` dropdown so labels + icons + ordering stay in sync.
const COMMISSIONER_TABS = [
  { value: "league-setup", label: "League Setup", icon: Trophy },
  { value: "player-pool", label: "Player Pool", icon: Users },
  { value: "rosters", label: "Rosters", icon: Shield },
  { value: "divisions", label: "League Structure", icon: Trophy },
  { value: "rules-schedule", label: "Transactions", icon: Sliders },
  { value: "salary-cap-contracts", label: "Salary Cap & Contracts", icon: DollarSign },
  { value: "scoring", label: "Scoring", icon: Target },
  { value: "draft", label: "Draft", icon: LayoutGrid },
  { value: "tanking", label: "Tank Monitor", icon: AlertTriangle },
  { value: "roster-monitor", label: "Roster Monitor", icon: ClipboardCheck },
  { value: "admin", label: "League Administration", icon: UserCog },
  { value: "audit-log", label: "Audit Log", icon: ScrollText },
] as const;


export default function CommissionerTabNavigation({ activeTab, onTabChange }: { activeTab: string; onTabChange: (tab: string) => void }) {
  return <>
          {/* Mobile-only tab selector. Below md the 13-item tab strip
              required heavy horizontal scrolling; a native-feeling
              dropdown gives one-tap access to every section. */}
          <div className="md:hidden">
            <label htmlFor="commissioner-settings-section" className="sr-only">Settings section</label>
            <select id="commissioner-settings-section" aria-label="Settings section"
              className="w-full min-h-11 rounded-md bg-secondary text-secondary-foreground border border-border px-3 text-sm"
              data-testid="commissioner-settings-mobile-tab-select" value={activeTab} onChange={event => onTabChange(event.target.value)}>
              {COMMISSIONER_TABS.map(({value,label}) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>

          {/* Desktop tab strip — hidden on mobile to reclaim the
              horizontal real-estate for the Select above. */}
          <TabsList className="hidden md:flex flex-wrap h-auto bg-secondary border border-border">
            <TabsTrigger value="league-setup" className="data-[state=active]:bg-primary/20">
              <Trophy className="h-4 w-4 mr-2" />
              League Setup
            </TabsTrigger>
            <TabsTrigger value="player-pool" className="data-[state=active]:bg-primary/20">
              <Users className="h-4 w-4 mr-2" />
              Player Pool
            </TabsTrigger>
            <TabsTrigger value="rosters" className="data-[state=active]:bg-primary/20">
              <Shield className="h-4 w-4 mr-2" />
              Rosters
            </TabsTrigger>
            <TabsTrigger value="divisions" className="data-[state=active]:bg-primary/20" data-testid="tab-divisions">
              <Trophy className="h-4 w-4 mr-2" />
              League Structure
            </TabsTrigger>
            <TabsTrigger value="rules-schedule" className="data-[state=active]:bg-primary/20" data-testid="tab-rules-schedule">
              <Sliders className="h-4 w-4 mr-2" />
              Transactions
            </TabsTrigger>
            <TabsTrigger value="salary-cap-contracts" className="data-[state=active]:bg-primary/20" data-testid="tab-salary-cap-contracts">
              <DollarSign className="h-4 w-4 mr-2" />
              Salary Cap & Contracts
            </TabsTrigger>
            <TabsTrigger value="scoring" className="data-[state=active]:bg-primary/20">
              <Target className="h-4 w-4 mr-2" />
              Scoring
            </TabsTrigger>
            <TabsTrigger value="draft" className="data-[state=active]:bg-primary/20">
              <LayoutGrid className="h-4 w-4 mr-2" />
              Draft
            </TabsTrigger>
            <TabsTrigger value="tanking" className="data-[state=active]:bg-primary/20">
              <AlertTriangle className="h-4 w-4 mr-2" />
              Tank Monitor
            </TabsTrigger>
            <TabsTrigger value="roster-monitor" className="data-[state=active]:bg-primary/20">
              <ClipboardCheck className="h-4 w-4 mr-2" />
              Roster Monitor
            </TabsTrigger>
            <TabsTrigger value="admin" className="data-[state=active]:bg-primary/20">
              <UserCog className="h-4 w-4 mr-2" />
              League Administration
            </TabsTrigger>
            <TabsTrigger value="audit-log" className="data-[state=active]:bg-primary/20">
              <ScrollText className="h-4 w-4 mr-2" />
              Audit Log
            </TabsTrigger>
          </TabsList>

  </>;
}
