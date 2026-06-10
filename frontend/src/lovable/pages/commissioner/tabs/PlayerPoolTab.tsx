// @ts-nocheck
/**
 * Iter 155 — Player Pool tab extracted from CommissionerSettings.tsx.
 *
 * Two cards:
 *   • Player Inclusion (Include-Entire-NHL switch, per-team checklist, conference toggles)
 *   • Pool Settings (lock pool, include minors, include unsigned, duplicate-players select)
 * All state is owned by the parent so cross-tab interactions stay intact.
 */
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

interface PlayerPoolTabProps {
  nhlTeams: string[];
  selectedTeams: string[];
  toggleTeam: (team: string) => void;
  duplicatePlayers: string;
  setDuplicatePlayers: (v: string) => void;
}

export default function PlayerPoolTab({
  nhlTeams,
  selectedTeams,
  toggleTeam,
  duplicatePlayers,
  setDuplicatePlayers,
}: PlayerPoolTabProps) {
  return (
    <div className="space-y-6" data-testid="commissioner-player-pool-tab">
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle>Player Inclusion</CardTitle>
          <CardDescription>Select which players are available in your league</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label>Include Entire NHL</Label>
              <p className="text-sm text-muted-foreground">All NHL players are available</p>
            </div>
            <Switch defaultChecked />
          </div>
          <Separator />
          <div className="space-y-3">
            <Label>Or Limit by Team</Label>
            <div className="grid gap-2 md:grid-cols-4" data-testid="player-pool-team-grid">
              {nhlTeams.map((team) => (
                <div key={team} className="flex items-center space-x-2">
                  <Checkbox
                    id={team}
                    checked={selectedTeams.includes(team)}
                    onCheckedChange={() => toggleTeam(team)}
                  />
                  <label htmlFor={team} className="text-sm cursor-pointer">{team}</label>
                </div>
              ))}
            </div>
          </div>
          <Separator />
          <div className="space-y-3">
            <Label>Limit by Conference</Label>
            <div className="flex gap-4">
              <div className="flex items-center space-x-2">
                <Checkbox id="eastern" defaultChecked />
                <label htmlFor="eastern" className="text-sm cursor-pointer">Eastern Conference</label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox id="western" defaultChecked />
                <label htmlFor="western" className="text-sm cursor-pointer">Western Conference</label>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle>Pool Settings</CardTitle>
          <CardDescription>Additional player pool configurations</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label>Lock Player Pool</Label>
              <p className="text-sm text-muted-foreground">Prevent changes to the player pool during season</p>
            </div>
            <Switch />
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <Label>Include Minor League Players</Label>
              <p className="text-sm text-muted-foreground">AHL and other minor league players available</p>
            </div>
            <Switch defaultChecked />
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <Label>Include Unsigned/Drafted Players</Label>
              <p className="text-sm text-muted-foreground">Players not on an NHL roster (drafted, European, etc.)</p>
            </div>
            <Switch />
          </div>
          <Separator />
          <div className="space-y-2">
            <Label>Duplicate Players for Selection</Label>
            <p className="text-sm text-muted-foreground">Allow the same player to be owned by multiple teams</p>
            <Select value={duplicatePlayers} onValueChange={setDuplicatePlayers}>
              <SelectTrigger
                className="bg-secondary border-border w-full sm:w-[280px]"
                data-testid="player-pool-duplicate-select"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="not-used">Not Used</SelectItem>
                <SelectItem value="entire-league">Entire League</SelectItem>
                <SelectItem value="across-divisions">Across Different Divisions</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
