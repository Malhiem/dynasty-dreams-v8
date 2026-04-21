// @ts-nocheck
interface DraftPick {
  year: number;
  round: number;
  original: string;
  projected: string;
}

const mockDraftPicks: DraftPick[] = [
  { year: 2025, round: 1, original: "Own", projected: "8-12" },
  { year: 2025, round: 1, original: "via Ice Breakers", projected: "1-5" },
  { year: 2025, round: 2, original: "Own", projected: "20-24" },
  { year: 2025, round: 3, original: "Own", projected: "32-36" },
  { year: 2026, round: 1, original: "Own", projected: "TBD" },
  { year: 2026, round: 2, original: "Own", projected: "TBD" },
];

const DraftPicks = () => {
  const groupedPicks = mockDraftPicks.reduce((acc, pick) => {
    if (!acc[pick.year]) acc[pick.year] = [];
    acc[pick.year].push(pick);
    return acc;
  }, {} as Record<number, DraftPick[]>);

  return (
    <div className="stat-card p-0 overflow-hidden">
      <div className="p-6 border-b border-border">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Draft Capital</h3>
          <span className="text-xs bg-accent/20 text-accent font-medium px-2 py-1 rounded-full">
            {mockDraftPicks.length} Picks
          </span>
        </div>
      </div>
      
      <div className="p-6 space-y-6">
        {Object.entries(groupedPicks).map(([year, picks], yearIndex) => (
          <div key={year} className="animate-slide-up" style={{ animationDelay: `${yearIndex * 100}ms` }}>
            <div className="flex items-center gap-2 mb-3">
              <span className="text-sm font-semibold text-foreground">{year}</span>
              <div className="flex-1 h-px bg-border" />
            </div>
            
            <div className="grid grid-cols-2 gap-2">
              {picks.map((pick, pickIndex) => (
                <div 
                  key={`${pick.year}-${pick.round}-${pickIndex}`}
                  className={`p-3 rounded-lg border transition-all hover:border-primary/30 ${
                    pick.round === 1 ? 'bg-accent/10 border-accent/30' : 'bg-secondary/50 border-border'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-xs font-bold ${pick.round === 1 ? 'text-accent' : 'text-muted-foreground'}`}>
                      Round {pick.round}
                    </span>
                    <span className="text-xs text-primary font-medium">#{pick.projected}</span>
                  </div>
                  <p className="text-xs text-muted-foreground truncate">{pick.original}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default DraftPicks;
