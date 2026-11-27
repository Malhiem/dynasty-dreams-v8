import React, { useState, useEffect } from 'react';
import { View, Text, FlatList, StyleSheet, SafeAreaView, RefreshControl, TouchableOpacity } from 'react-native';
import api from '../lib/api';
import { useLeague } from '../contexts/LeagueContext';
import LeagueSwitcher from '../components/LeagueSwitcher';
import LoadError from '../components/LoadError';
import { loadFailure, showActionError } from '../lib/errors';
import { leagueCapEnabled, salaryByPlayer, formatMillions } from '../lib/cap';
import TeamCapCard from '../components/TeamCapCard';
import RetentionPicker from '../components/RetentionPicker';
import { useAuth } from '../contexts/AuthContext';
import TeamLogoUploader from '../components/TeamLogoUploader';

export default function RosterScreen({ navigation }) {
  const { user } = useAuth();
  const { leagueId, league } = useLeague();
  const [team, setTeam] = useState(null);
  const [roster, setRoster] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [capEnabled, setCapEnabled] = useState(false);
  const [compliance, setCompliance] = useState(null);
  const [salaries, setSalaries] = useState({});
  const [retention, setRetention] = useState('no_preference');
  const [savingRetention, setSavingRetention] = useState(false);

  const fetchRoster = async () => {
    setLoadError(null);
    try {
      if (leagueId) {
        // "No cap, no salaries": cap figures only exist for leagues with a cap.
        const cap = leagueCapEnabled(league);
        setCapEnabled(cap);
        const { data: teams } = await api.get(`/teams?league_id=${leagueId}`);
        const myTeam = teams.find(t => t.owner_id === user?.id);
        if (myTeam) {
          setTeam(myTeam);
          setRetention(myTeam.salary_retention_pref || 'no_preference');
          const { data } = await api.get(`/roster/${myTeam.id}`);
          setRoster(data.players || []);
          if (cap) {
            try {
              const [comp, detail] = await Promise.all([
                api.get(`/teams/${myTeam.id}/compliance`),
                api.get(`/roster/${myTeam.id}/detail`),
              ]);
              setCompliance(comp.data);
              setSalaries(salaryByPlayer(detail.data, true));
            } catch (e) {
              setLoadError(loadFailure(e, 'salary cap details'));
            }
          } else {
            setCompliance(null);
            setSalaries({});
          }
        }
      }
    } catch (e) { setLoadError(loadFailure(e, 'your roster')); }
    setLoading(false);
  };

  useEffect(() => { setTeam(null); setRoster([]); setCompliance(null); setSalaries({}); fetchRoster(); }, [leagueId]);

  const updateRetention = async (next) => {
    if (!team || savingRetention) return;
    const prev = retention;
    setRetention(next);
    setSavingRetention(true);
    try {
      await api.put(`/teams/${team.id}/trade-block-preference`, { preference: next });
    } catch (e) {
      setRetention(prev);
      showActionError(e, 'Could not update salary retention');
    }
    setSavingRetention(false);
  };

  return (
    <SafeAreaView style={s.container}>
      <LeagueSwitcher />
      <View style={s.header}>
        {team ? (
          <TeamLogoUploader
            teamId={team.id}
            name={team.name}
            abbr={team.logo_abbr}
            logo={team.logo_url}
            size="lg"
            onChange={(newLogo) => setTeam(prev => prev ? { ...prev, logo_url: newLogo } : prev)}
          />
        ) : null}
        <View style={s.headerInfo}>
          <Text style={s.title}>{team?.name || 'My Roster'}</Text>
          <Text style={s.subtitle}>{roster.length} players</Text>
        </View>
      </View>

      <View style={s.proStrip}>
        <TouchableOpacity
          testID="goto-trade-analyzer"
          style={[s.proBtn, { borderColor: '#00D2FF' }]}
          onPress={() => navigation.navigate('TradeAnalyzer', { leagueId: team?.league_id })}
        >
          <Text style={[s.proBtnText, { color: '#00D2FF' }]}>⚖ Trade Analyzer</Text>
        </TouchableOpacity>
        <TouchableOpacity
          testID="goto-projections"
          style={[s.proBtn, { borderColor: '#FFB020' }]}
          onPress={() => navigation.navigate('Projections', { leagueId: team?.league_id })}
        >
          <Text style={[s.proBtnText, { color: '#FFB020' }]}>📈 Projections</Text>
        </TouchableOpacity>
      </View>
      <View style={s.proStrip}>
        <TouchableOpacity testID="goto-trade-block" style={[s.proBtn, { borderColor: '#A1A1AA' }]} onPress={() => navigation.navigate('TradeBlock')}>
          <Text style={[s.proBtnText, { color: '#fff' }]}>🔄 Trade Block</Text>
        </TouchableOpacity>
        <TouchableOpacity testID="goto-waivers" style={[s.proBtn, { borderColor: '#A1A1AA' }]} onPress={() => navigation.navigate('Waivers')}>
          <Text style={[s.proBtnText, { color: '#fff' }]}>📋 Waivers</Text>
        </TouchableOpacity>
        {capEnabled ? (
          <TouchableOpacity testID="goto-salary-cap" style={[s.proBtn, { borderColor: '#34C759' }]} onPress={() => navigation.navigate('SalaryCap')}>
            <Text style={[s.proBtnText, { color: '#34C759' }]}>💰 Salary Cap</Text>
          </TouchableOpacity>
        ) : null}
      </View>
      <LoadError message={loadError} onRetry={fetchRoster} />
      <FlatList
        data={roster}
        ListHeaderComponent={capEnabled ? (
          <View>
            <TeamCapCard compliance={compliance} />
            {team ? <RetentionPicker value={retention} onChange={updateRetention} disabled={savingRetention} /> : null}
          </View>
        ) : null}
        keyExtractor={item => item.player_id}
        renderItem={({ item }) => (
          <View style={s.row}>
            <View style={s.posBadge}><Text style={s.posText}>{item.position}</Text></View>
            <View style={s.info}>
              <Text style={s.name}>{item.name}</Text>
              <Text style={s.meta}>{item.nhl_team} · {item.games_played}GP {item.goals}G {item.assists}A</Text>
            </View>
            {capEnabled && salaries[String(item.player_id)] != null ? (
              <View style={s.salaryCol} testID="roster-salary">
                <Text style={s.salaryVal}>{formatMillions(salaries[String(item.player_id)])}</Text>
                <Text style={s.fptsLabel}>SALARY</Text>
              </View>
            ) : null}
            <View style={s.fptsCol}>
              <Text style={s.fptsVal}>{item.fantasy_points?.toFixed(1) || '—'}</Text>
              <Text style={s.fptsLabel}>FPTS</Text>
            </View>
          </View>
        )}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={fetchRoster} tintColor="#00D2FF" />}
        ListEmptyComponent={<View style={s.empty}><Text style={s.emptyText}>{loading ? 'Loading...' : loadError ? '' : 'Empty roster'}</Text></View>}
        contentContainerStyle={s.list}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  header: {
    padding: 20, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.1)',
    flexDirection: 'row', alignItems: 'center', gap: 16,
  },
  headerInfo: { flex: 1 },
  title: { fontSize: 24, fontWeight: '800', color: '#fff' },
  subtitle: { fontSize: 13, color: '#A1A1AA', marginTop: 4 },
  list: { padding: 8 },
  row: { flexDirection: 'row', alignItems: 'center', padding: 12, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)' },
  posBadge: { width: 36, height: 36, borderRadius: 8, backgroundColor: '#00D2FF20', alignItems: 'center', justifyContent: 'center' },
  posText: { color: '#00D2FF', fontSize: 12, fontWeight: '700' },
  info: { flex: 1, marginLeft: 12 },
  name: { color: '#fff', fontSize: 14, fontWeight: '600' },
  meta: { color: '#A1A1AA', fontSize: 11, marginTop: 2 },
  fptsCol: { alignItems: 'center', minWidth: 44 },
  salaryCol: { alignItems: 'center', marginRight: 14 },
  salaryVal: { color: '#fff', fontSize: 13, fontWeight: '700' },
  fptsVal: { color: '#00D2FF', fontSize: 16, fontWeight: '800' },
  fptsLabel: { color: '#A1A1AA', fontSize: 9, letterSpacing: 1 },
  proStrip: { flexDirection: 'row', gap: 8, padding: 10, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)' },
  proBtn: { flex: 1, borderWidth: 1, borderRadius: 10, paddingVertical: 8, alignItems: 'center', backgroundColor: 'rgba(255,255,255,0.03)' },
  proBtnText: { fontSize: 12, fontWeight: '700' },
  empty: { alignItems: 'center', paddingTop: 60 },
  emptyText: { color: '#A1A1AA' },
});
