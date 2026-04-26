// @ts-nocheck
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MapPin, Calendar, Ruler, Weight, Trophy, DollarSign, Award, Crown, TrendingUp, Layers } from "lucide-react";

const formatHeight = (inches) => {
  if (!inches) return "—";
  const f = Math.floor(inches / 12);
  const i = inches % 12;
  return `${f}' ${i}"`;
};

const formatBirthDate = (iso) => {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const age = Math.floor((Date.now() - d.getTime()) / (365.25 * 86400 * 1000));
    return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()} (${age})`;
  } catch { return iso; }
};

const formatBirthplace = (player) => {
  const parts = [player.birth_city, player.birth_state, player.birth_country].filter(Boolean);
  return parts.length ? parts.join(", ") : "—";
};

const formatDraft = (player) => {
  if (!player.draft_year) return "Undrafted";
  const round = player.draft_round ? `${ordinal(player.draft_round)} round` : "?";
  const overall = player.draft_overall ? `${ordinal(player.draft_overall)} overall` : "";
  const team = player.draft_team_abbr || "";
  return `${player.draft_year} · ${round} / ${overall} · ${team}`.replace(/\s+\/\s+\s+·/, " ·");
};

const ordinal = (n) => {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

const formatMoney = (n) => {
  if (n === null || n === undefined) return "—";
  return n >= 1000000 ? `$${(n / 1000000).toFixed(2)}M` : `$${n.toLocaleString()}`;
};

function Field({ icon: Icon, label, value, accent }) {
  return (
    <div className="flex items-start gap-2.5 min-w-0">
      <div className="h-8 w-8 rounded-lg bg-[#1A1A1A] border border-white/5 flex items-center justify-center shrink-0">
        <Icon className="h-3.5 w-3.5 text-[#A1A1AA]" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[10px] uppercase tracking-widest text-[#71717A]">{label}</p>
        <p className={`text-sm font-semibold truncate ${accent ? "text-[#00D2FF]" : "text-white"}`}>{value || "—"}</p>
      </div>
    </div>
  );
}

/**
 * PlayerBioBar — the rich detail strip below the player profile header.
 * Shows: birthplace, height, birthdate (+age), weight, NHL seasons,
 * cap hit, AAV, salary, draft info, owner in active league, total fantasy
 * points, FPTS/game, position eligibility, minors-eligible flag.
 */
export default function PlayerBioBar({ player }) {
  if (!player) return null;
  const cap = player.cap_hit ?? null;
  const aav = player.aav ?? null;
  const salary = player.salary ?? null;
  return (
    <Card className="border-white/10" data-testid="player-bio-bar">
      <CardContent className="p-5">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          <Field icon={MapPin} label="Birthplace" value={formatBirthplace(player)} />
          <Field icon={Ruler} label="Height" value={formatHeight(player.height_inches)} />
          <Field icon={Calendar} label="Birthdate" value={formatBirthDate(player.birth_date)} />
          <Field icon={Weight} label="Weight" value={player.weight_pounds ? `${player.weight_pounds} lbs` : "—"} />
          <Field icon={Trophy} label="NHL Seasons" value={player.nhl_seasons || "—"} />

          <Field icon={DollarSign} label="Cap Hit" value={formatMoney(cap)} />
          <Field icon={DollarSign} label="AAV" value={formatMoney(aav)} />
          <Field icon={DollarSign} label="Salary" value={formatMoney(salary)} />
          <div className="col-span-2 lg:col-span-2 xl:col-span-2 flex items-start gap-2.5 min-w-0">
            <div className="h-8 w-8 rounded-lg bg-[#FFB020]/15 border border-[#FFB020]/20 flex items-center justify-center shrink-0">
              <Award className="h-3.5 w-3.5 text-[#FFB020]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[10px] uppercase tracking-widest text-[#71717A]">Drafted</p>
              <p className="text-sm font-semibold text-white truncate" data-testid="player-bio-draft">{formatDraft(player)}</p>
            </div>
          </div>

          <Field icon={Crown} label="Owned by" value={player.owned_by_team_name || "Free Agent"} accent={!!player.owned_by_team_name} />
          <Field icon={Trophy} label="Total FPTS" value={player.fantasy_points != null ? player.fantasy_points.toFixed(1) : "—"} accent />
          <Field icon={TrendingUp} label="FPTS / GP" value={player.fantasy_points_per_game != null ? player.fantasy_points_per_game.toFixed(2) : "—"} accent />

          <div className="flex items-start gap-2.5 min-w-0">
            <div className="h-8 w-8 rounded-lg bg-[#1A1A1A] border border-white/5 flex items-center justify-center shrink-0">
              <Layers className="h-3.5 w-3.5 text-[#A1A1AA]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[10px] uppercase tracking-widest text-[#71717A]">Position Eligibility</p>
              <div className="flex flex-wrap gap-1 mt-0.5" data-testid="player-bio-eligible">
                {(player.eligible_positions || [player.position]).map((p) => (
                  <Badge key={p} variant="outline" className="border-white/15 text-white text-[10px]">{p}</Badge>
                ))}
              </div>
            </div>
          </div>

          <div className="flex items-start gap-2.5 min-w-0">
            <div className="h-8 w-8 rounded-lg bg-[#1A1A1A] border border-white/5 flex items-center justify-center shrink-0">
              <Trophy className="h-3.5 w-3.5 text-[#A1A1AA]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[10px] uppercase tracking-widest text-[#71717A]">Minors Eligible</p>
              <p className="text-sm font-semibold" data-testid="player-bio-minors">
                {player.minors_eligible ? (
                  <span className="text-emerald-400">Yes</span>
                ) : (
                  <span className="text-[#A1A1AA]">No</span>
                )}
                {player.minors_criteria && (
                  <span className="ml-2 text-[10px] text-[#71717A] font-normal">
                    {player.minors_criteria.career_games}GP / {player.minors_criteria.age}y
                  </span>
                )}
              </p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
