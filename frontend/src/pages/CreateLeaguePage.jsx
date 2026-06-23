import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api, { formatApiError } from '@/lib/api';
import { AppLayout } from '@/components/layout/AppLayout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Trophy, ArrowLeft, Calendar } from '@phosphor-icons/react';

const LEAGUE_FORMATS = [
  { value: 'redraft', label: 'Redraft', desc: 'Draft new team every season' },
  { value: 'keeper', label: 'Keeper', desc: 'Keep select players year-over-year' },
  { value: 'dynasty', label: 'Dynasty', desc: 'Keep entire roster indefinitely' },
  { value: 'best_ball', label: 'Best Ball', desc: 'Auto-optimized lineups, no management' },
];

const SCORING_FORMATS = [
  { value: 'head_to_head', label: 'Head-to-Head', desc: 'Weekly 1v1 matchups' },
  { value: 'total_points', label: 'Total Points', desc: 'Season-long point accumulation' },
  { value: 'rotisserie', label: 'Rotisserie', desc: 'Category-based ranking' },
  { value: 'guillotine', label: 'Guillotine', desc: 'Lowest score eliminated weekly' },
  { value: 'all_play', label: 'All-Play', desc: 'Play every team every week' },
];

const DRAFT_TYPES = [
  { value: 'snake', label: 'Snake Draft' },
  { value: 'linear', label: 'Linear Draft' },
  { value: 'auction', label: 'Auction Draft' },
  { value: 'custom', label: 'Custom Draft' },
];

export default function CreateLeaguePage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [previewError, setPreviewError] = useState('');
  const [form, setForm] = useState({
    name: '',
    format: 'dynasty',
    scoring_format: 'head_to_head',
    max_teams: 12,
    salary_cap_enabled: false,
    salary_cap: 100,
    draft_type: 'snake',
    roster_spots: 20,
    keepers_allowed: 0,
    entry_fee: 0,
    is_private: false,
    // Iter 219 — H2H only: number of matchups per team per week (max N-1)
    matchups_per_week: 1,
  });

  const updateForm = (key, value) => {
    setForm(prev => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const payload = {
        ...form,
        entry_fee: form.entry_fee > 0 ? form.entry_fee : null,
        salary_cap: form.salary_cap_enabled ? form.salary_cap : null,
      };
      const { data } = await api.post('/leagues', payload);
      navigate(`/leagues/${data.id}`);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const handlePreview = async () => {
    setPreviewError('');
    setPreviewLoading(true);
    setPreviewOpen(true);
    try {
      const { data } = await api.post('/matchups/preview', {
        max_teams: form.max_teams,
        matchups_per_week: form.matchups_per_week,
        num_weeks: 4,
      });
      setPreviewData(data);
    } catch (err) {
      setPreviewError(formatApiError(err));
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <AppLayout>
    <div data-testid="create-league-page">
      <div className="max-w-3xl mx-auto">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-[#A1A1AA] hover:text-white mb-6"
        >
          <ArrowLeft size={20} />
          Back
        </button>

        <div className="flex items-center gap-4 mb-8">
          <div className="p-3 bg-[#00D2FF]/20 rounded">
            <Trophy size={32} weight="duotone" className="text-[#00D2FF]" />
          </div>
          <div>
            <h1 className="font-heading text-3xl font-bold tracking-tight text-white">CREATE LEAGUE</h1>
            <p className="text-[#A1A1AA]">Set up your custom fantasy league</p>
          </div>
        </div>

        {error && (
          <div className="bg-[#FF3B30]/20 border border-[#FF3B30]/50 text-[#FF3B30] px-4 py-3 rounded mb-6">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Basic Info */}
          <div className="surface p-6">
            <h2 className="font-heading text-xl font-bold text-white mb-6">BASIC INFORMATION</h2>
            <div className="space-y-4">
              <div>
                <Label className="text-[#A1A1AA]">League Name</Label>
                <Input
                  value={form.name}
                  onChange={(e) => updateForm('name', e.target.value)}
                  placeholder="Enter league name"
                  required
                  data-testid="league-name"
                  className="mt-2 bg-[#0A0A0A] border-white/10 text-white"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <Label className="text-[#A1A1AA]">Max Teams</Label>
                  <Select value={form.max_teams.toString()} onValueChange={(v) => updateForm('max_teams', parseInt(v))}>
                    <SelectTrigger className="mt-2 bg-[#0A0A0A] border-white/10 text-white" data-testid="max-teams">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-[#141414] border-white/10">
                      {[4, 6, 8, 10, 12, 14, 16, 20, 24, 32].map(n => (
                        <SelectItem key={n} value={n.toString()} className="text-white hover:bg-white/10">{n} Teams</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-[#A1A1AA]">Roster Spots</Label>
                  <Input
                    type="number"
                    min={10}
                    max={30}
                    value={form.roster_spots}
                    onChange={(e) => updateForm('roster_spots', parseInt(e.target.value))}
                    data-testid="roster-spots"
                    className="mt-2 bg-[#0A0A0A] border-white/10 text-white"
                  />
                </div>
              </div>

              <div className="flex items-center justify-between p-4 bg-[#0A0A0A] rounded">
                <div>
                  <p className="text-white font-medium">Private League</p>
                  <p className="text-sm text-[#A1A1AA]">Require invite code to join</p>
                </div>
                <Switch
                  checked={form.is_private}
                  onCheckedChange={(v) => updateForm('is_private', v)}
                  data-testid="is-private"
                />
              </div>
            </div>
          </div>

          {/* League Format */}
          <div className="surface p-6">
            <h2 className="font-heading text-xl font-bold text-white mb-6">LEAGUE FORMAT</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {LEAGUE_FORMATS.map(({ value, label, desc }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => updateForm('format', value)}
                  data-testid={`format-${value}`}
                  className={`p-4 rounded border text-left transition-colors ${
                    form.format === value
                      ? 'border-[#00D2FF] bg-[#00D2FF]/10'
                      : 'border-white/10 hover:border-white/20'
                  }`}
                >
                  <p className={`font-semibold ${form.format === value ? 'text-[#00D2FF]' : 'text-white'}`}>{label}</p>
                  <p className="text-sm text-[#A1A1AA]">{desc}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Scoring Format */}
          <div className="surface p-6">
            <h2 className="font-heading text-xl font-bold text-white mb-6">SCORING FORMAT</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {SCORING_FORMATS.map(({ value, label, desc }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => updateForm('scoring_format', value)}
                  data-testid={`scoring-${value}`}
                  className={`p-4 rounded border text-left transition-colors ${
                    form.scoring_format === value
                      ? 'border-[#00D2FF] bg-[#00D2FF]/10'
                      : 'border-white/10 hover:border-white/20'
                  }`}
                >
                  <p className={`font-semibold ${form.scoring_format === value ? 'text-[#00D2FF]' : 'text-white'}`}>{label}</p>
                  <p className="text-sm text-[#A1A1AA]">{desc}</p>
                </button>
              ))}
            </div>

            {/* Iter 219 — H2H matchups per week (range 1 .. max_teams-1) */}
            {form.scoring_format.startsWith('head_to_head') && (
              <div className="mt-4 pt-4 border-t border-white/10" data-testid="matchups-per-week-block">
                <Label className="text-[#A1A1AA]">Matchups per week</Label>
                <p className="text-xs text-[#A1A1AA] mt-1 mb-2">
                  Each team plays this many opponents every scoring week. Max = teams − 1 ({form.max_teams - 1}).
                </p>
                <Select
                  value={String(form.matchups_per_week)}
                  onValueChange={(v) => updateForm('matchups_per_week', parseInt(v, 10))}
                >
                  <SelectTrigger className="bg-[#0A0A0A] border-white/10 text-white max-w-[180px]" data-testid="matchups-per-week">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-[#141414] border-white/10">
                    {Array.from({ length: form.max_teams - 1 }, (_, i) => i + 1).map((n) => (
                      <SelectItem key={n} value={String(n)}>
                        {n} {n === 1 ? 'matchup' : 'matchups'}/week
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {/* Draft & Salary */}
          <div className="surface p-6">
            <h2 className="font-heading text-xl font-bold text-white mb-6">DRAFT & SALARY</h2>
            <div className="space-y-4">
              <div>
                <Label className="text-[#A1A1AA]">Draft Type</Label>
                <Select value={form.draft_type} onValueChange={(v) => updateForm('draft_type', v)}>
                  <SelectTrigger className="mt-2 bg-[#0A0A0A] border-white/10 text-white" data-testid="draft-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-[#141414] border-white/10">
                    {DRAFT_TYPES.map(({ value, label }) => (
                      <SelectItem key={value} value={value} className="text-white hover:bg-white/10">{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between p-4 bg-[#0A0A0A] rounded">
                <div>
                  <p className="text-white font-medium">Salary Cap</p>
                  <p className="text-sm text-[#A1A1AA]">Enable contract management</p>
                </div>
                <Switch
                  checked={form.salary_cap_enabled}
                  onCheckedChange={(v) => updateForm('salary_cap_enabled', v)}
                  data-testid="salary-cap-enabled"
                />
              </div>

              {form.salary_cap_enabled && (
                <div>
                  <Label className="text-[#A1A1AA]">Salary Cap Amount ($)</Label>
                  <Input
                    type="number"
                    min={1}
                    value={form.salary_cap}
                    onChange={(e) => updateForm('salary_cap', parseFloat(e.target.value))}
                    data-testid="salary-cap-amount"
                    className="mt-2 bg-[#0A0A0A] border-white/10 text-white"
                  />
                </div>
              )}

              {(form.format === 'keeper' || form.format === 'dynasty') && (
                <div>
                  <Label className="text-[#A1A1AA]">Keepers Allowed</Label>
                  <Input
                    type="number"
                    min={0}
                    max={10}
                    value={form.keepers_allowed}
                    onChange={(e) => updateForm('keepers_allowed', parseInt(e.target.value))}
                    data-testid="keepers-allowed"
                    className="mt-2 bg-[#0A0A0A] border-white/10 text-white"
                  />
                </div>
              )}
            </div>
          </div>

          {/* Entry Fee */}
          <div className="surface p-6">
            <h2 className="font-heading text-xl font-bold text-white mb-6">ENTRY FEE</h2>
            <div>
              <Label className="text-[#A1A1AA]">Entry Fee ($)</Label>
              <Input
                type="number"
                min={0}
                step={0.01}
                value={form.entry_fee}
                onChange={(e) => updateForm('entry_fee', parseFloat(e.target.value) || 0)}
                placeholder="0 for free league"
                data-testid="entry-fee"
                className="mt-2 bg-[#0A0A0A] border-white/10 text-white"
              />
              <p className="text-sm text-[#A1A1AA] mt-2">Leave at 0 for a free league</p>
            </div>
          </div>

          {/* Preview + Submit */}
          <div className="flex flex-col sm:flex-row gap-3">
            <Button
              type="button"
              onClick={handlePreview}
              disabled={!form.scoring_format.startsWith('head_to_head')}
              data-testid="preview-schedule-btn"
              variant="outline"
              className="sm:w-1/3 border-white/20 text-white hover:bg-white/5 py-6 text-base disabled:opacity-40"
              title={!form.scoring_format.startsWith('head_to_head')
                ? 'Schedule preview is available for head-to-head leagues only'
                : 'See the first 4 weeks of matchups based on your current settings'}
            >
              <Calendar size={18} className="mr-2" />
              Preview schedule
            </Button>
            <Button
              type="submit"
              disabled={loading || !form.name}
              data-testid="create-league-submit"
              className="flex-1 bg-[#00D2FF] text-black font-semibold hover:bg-[#33DBFF] disabled:opacity-50 py-6 text-lg"
            >
              {loading ? 'Creating League...' : 'Create League'}
            </Button>
          </div>
        </form>

        {/* Iter 221 — Schedule Preview Dialog */}
        <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
          <DialogContent className="bg-[#0A0A0A] border-white/10 text-white max-w-2xl max-h-[80vh] overflow-y-auto" data-testid="preview-schedule-dialog">
            <DialogHeader>
              <DialogTitle className="text-white">Schedule Preview — first 4 weeks</DialogTitle>
              <DialogDescription className="text-[#A1A1AA]">
                {form.max_teams} teams · {form.matchups_per_week} matchup{form.matchups_per_week > 1 ? 's' : ''}/week · placeholder team names
              </DialogDescription>
            </DialogHeader>
            {previewLoading && (
              <div className="p-8 text-center text-[#A1A1AA]" data-testid="preview-loading">
                Building schedule…
              </div>
            )}
            {previewError && (
              <div className="bg-[#FF3B30]/20 border border-[#FF3B30]/50 text-[#FF3B30] px-4 py-3 rounded" data-testid="preview-error">
                {previewError}
              </div>
            )}
            {!previewLoading && !previewError && previewData && (
              <div className="space-y-4" data-testid="preview-weeks">
                {previewData.weeks.map((wk) => (
                  <div key={wk.week} className="surface p-4" data-testid={`preview-week-${wk.week}`}>
                    <h4 className="font-heading text-sm font-bold text-[#00D2FF] mb-2">WEEK {wk.week}</h4>
                    {wk.matchups.length === 0 ? (
                      <p className="text-xs text-[#A1A1AA]">— bye week —</p>
                    ) : (
                      <ul className="space-y-1 text-sm">
                        {wk.matchups.map((m, idx) => (
                          <li key={idx} className="flex items-center justify-between text-white/90">
                            <span>{m.home_team_name}</span>
                            <span className="text-[#A1A1AA]">vs</span>
                            <span>{m.away_team_name}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
                <p className="text-xs text-[#A1A1AA] text-center pt-2">
                  Total of {previewData.total_matchups} matchups across {previewData.weeks.length} weeks
                </p>
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>
    </div>
    </AppLayout>
  );
}
