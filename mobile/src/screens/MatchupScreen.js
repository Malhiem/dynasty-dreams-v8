import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, SafeAreaView, RefreshControl, TouchableOpacity } from 'react-native';
import api from '../lib/api';

export default function MatchupScreen({ route }) {
  const initialLeagueId = route?.params?.leagueId;
  const [leagues, setLeagues] = useState([]);
  const [leagueId, setLeagueId] = useState(initialLeagueId || null);
  const [data, setData] = useState({ week: null, matchups: [] });
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (lid) => {
    if (!lid) return;
    try {
      const { data: cw } = await api.get(`/matchups/${lid}/current-week`);
      setData(cw);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data: ls } = await api.get('/leagues?my_leagues=true');
        if (cancelled) return;
        setLeagues(ls || []);
        const id = leagueId || ls?.[0]?.id;
        if (id) {
          setLeagueId(id);
          await load(id);
        }
      } catch (e) { console.error(e); }
    })();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onRefresh = async () => { setRefreshing(true); await load(leagueId); setRefreshing(false); };

  const switchLeague = async (id) => { setLeagueId(id); await load(id); };

  return (
    <SafeAreaView style={s.container}>
      <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#00D2FF" />}>
        <View style={s.header}>
          <Text style={s.title}>MATCHUPS</Text>
          {data.week && <Text style={s.week}>Week {data.week}</Text>}
        </View>

        {leagues.length > 1 && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.tabs} contentContainerStyle={s.tabsInner}>
            {leagues.map(l => (
              <TouchableOpacity
                key={l.id}
                onPress={() => switchLeague(l.id)}
                style={[s.tab, leagueId === l.id && s.tabActive]}
              >
                <Text style={[s.tabText, leagueId === l.id && s.tabTextActive]} numberOfLines={1}>{l.name}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        )}

        {data.matchups.length === 0 ? (
          <View style={s.emptyCard}>
            <Text style={s.emptyText}>No matchups scheduled for this week.</Text>
          </View>
        ) : (
          data.matchups.map(m => {
            const winner = m.winner;
            const homeWon = winner === m.home_team_id;
            const awayWon = winner === m.away_team_id;
            return (
              <View key={m._id} style={s.matchupCard} testID={`matchup-${m._id}`}>
                <View style={[s.teamRow, homeWon && s.winnerRow]}>
                  <Text style={[s.teamName, homeWon && s.winnerText]}>{m.home_team_name}</Text>
                  <Text style={[s.score, homeWon && s.winnerText]}>{m.home_score?.toFixed(1) ?? '–'}</Text>
                </View>
                <View style={s.divider} />
                <View style={[s.teamRow, awayWon && s.winnerRow]}>
                  <Text style={[s.teamName, awayWon && s.winnerText]}>{m.away_team_name}</Text>
                  <Text style={[s.score, awayWon && s.winnerText]}>{m.away_score?.toFixed(1) ?? '–'}</Text>
                </View>
                <View style={s.statusRow}>
                  <Text style={[s.statusBadge, m.status === 'completed' ? s.statusFinal : s.statusUpcoming]}>
                    {m.status?.toUpperCase() || 'SCHEDULED'}
                  </Text>
                  {m.bracket && (
                    <Text style={s.bracketBadge}>
                      {m.is_final ? '🏆 ' : ''}{m.bracket.replace(/_/g, ' ').toUpperCase()}
                    </Text>
                  )}
                </View>
              </View>
            );
          })
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  header: { paddingHorizontal: 20, paddingTop: 20, paddingBottom: 12, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  title: { color: '#fff', fontSize: 24, fontWeight: '900', letterSpacing: -0.5 },
  week: { color: '#00D2FF', fontSize: 14, fontWeight: '700' },
  tabs: { paddingLeft: 16, marginBottom: 12, maxHeight: 40 },
  tabsInner: { gap: 8, paddingRight: 16 },
  tab: { backgroundColor: '#141414', borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 6 },
  tabActive: { backgroundColor: '#00D2FF20', borderColor: '#00D2FF' },
  tabText: { color: '#A1A1AA', fontSize: 12, fontWeight: '600', maxWidth: 140 },
  tabTextActive: { color: '#00D2FF' },
  matchupCard: { marginHorizontal: 16, marginBottom: 10, backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)', overflow: 'hidden' },
  teamRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14 },
  winnerRow: { backgroundColor: '#00D2FF10' },
  teamName: { color: '#fff', fontSize: 14, fontWeight: '600', flex: 1 },
  score: { color: '#fff', fontSize: 18, fontWeight: '900' },
  winnerText: { color: '#00D2FF' },
  divider: { height: 1, backgroundColor: 'rgba(255,255,255,0.08)' },
  statusRow: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 14, paddingVertical: 8, backgroundColor: 'rgba(0,0,0,0.3)' },
  statusBadge: { fontSize: 9, fontWeight: '900', letterSpacing: 0.8, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  statusFinal: { color: '#34d399', backgroundColor: '#34d39922' },
  statusUpcoming: { color: '#A1A1AA', backgroundColor: 'rgba(255,255,255,0.06)' },
  bracketBadge: { color: '#fbbf24', fontSize: 9, fontWeight: '900', letterSpacing: 0.8 },
  emptyCard: { margin: 16, padding: 32, backgroundColor: '#141414', borderRadius: 8, alignItems: 'center', borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)' },
  emptyText: { color: '#A1A1AA', fontSize: 14 },
});
