import React, { useState, useEffect } from 'react';
import { View, Text, FlatList, StyleSheet, SafeAreaView, RefreshControl } from 'react-native';
import api from '../lib/api';
import TeamLogo from '../components/TeamLogo';

export default function StandingsScreen({ route }) {
  const leagueId = route?.params?.leagueId;
  const [standings, setStandings] = useState([]);
  const [matchups, setMatchups] = useState([]);
  const [teamsById, setTeamsById] = useState({});
  const [week, setWeek] = useState(1);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    if (!leagueId) {
      try { const { data } = await api.get('/leagues?my_leagues=true'); if (data[0]) await fetchForLeague(data[0].id); } catch (e) {}
    } else { await fetchForLeague(leagueId); }
    setLoading(false);
  };

  const fetchForLeague = async (lid) => {
    try {
      const [st, wk, tm] = await Promise.all([
        api.get(`/leagues/${lid}/standings`),
        api.get(`/matchups/${lid}/current-week`),
        api.get(`/teams?league_id=${lid}`),
      ]);
      setStandings(st.data);
      setWeek(wk.data.week);
      setMatchups(wk.data.matchups || []);
      const map = {};
      (tm.data || []).forEach(t => { map[t.id] = t; });
      setTeamsById(map);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { fetchData(); }, [leagueId]);

  return (
    <SafeAreaView style={s.container}>
      <FlatList
        data={standings}
        keyExtractor={item => item.team_id}
        ListHeaderComponent={<>
          <Text style={s.sectionTitle}>STANDINGS</Text>
          {standings.map((t, i) => {
            const teamData = teamsById[t.team_id];
            return (
              <View key={t.team_id} style={[s.standingRow, i === 0 && s.firstRow]}>
                <Text style={[s.rank, i === 0 && s.rankFirst]}>{t.rank}</Text>
                <TeamLogo
                  logo={teamData?.logo_url}
                  name={t.team_name}
                  abbr={teamData?.logo_abbr}
                  size="sm"
                />
                <View style={s.info}><Text style={s.teamName}>{t.team_name}</Text><Text style={s.owner}>{t.owner_name}</Text></View>
                <Text style={s.record}>{t.wins}W-{t.losses}L</Text>
                <Text style={s.pf}>{(t.points_for || 0).toFixed(0)} PF</Text>
              </View>
            );
          })}
          <Text style={[s.sectionTitle, { marginTop: 24 }]}>WEEK {week} MATCHUPS</Text>
        </>}
        data={matchups}
        renderItem={({ item }) => {
          const homeT = teamsById[item.home_team_id];
          const awayT = teamsById[item.away_team_id];
          return (
            <View style={s.matchupCard}>
              <View style={s.matchupSide}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <TeamLogo logo={homeT?.logo_url} name={item.home_team_name} abbr={homeT?.logo_abbr} size="sm" />
                  <Text style={[s.matchupTeam, item.home_score > item.away_score && s.winner]} numberOfLines={1}>{item.home_team_name}</Text>
                </View>
              </View>
              <View style={s.scoreBox}>
                {item.status === 'completed' ? <Text style={s.score}>{item.home_score} - {item.away_score}</Text> : <Text style={s.vs}>VS</Text>}
              </View>
              <View style={[s.matchupSide, { alignItems: 'flex-end' }]}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Text style={[s.matchupTeam, item.away_score > item.home_score && s.winner]} numberOfLines={1}>{item.away_team_name}</Text>
                  <TeamLogo logo={awayT?.logo_url} name={item.away_team_name} abbr={awayT?.logo_abbr} size="sm" />
                </View>
              </View>
            </View>
          );
        }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={fetchData} tintColor="#00D2FF" />}
        contentContainerStyle={s.list}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  list: { padding: 16 },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: '#A1A1AA', marginBottom: 12, letterSpacing: 1 },
  standingRow: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: '#141414', borderRadius: 8, marginBottom: 6, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)', gap: 8 },
  firstRow: { borderColor: '#00D2FF40', backgroundColor: '#00D2FF10' },
  rank: { fontSize: 18, fontWeight: '800', color: '#A1A1AA', width: 30, textAlign: 'center' },
  rankFirst: { color: '#00D2FF' },
  info: { flex: 1, marginLeft: 8 },
  teamName: { color: '#fff', fontSize: 14, fontWeight: '600' },
  owner: { color: '#A1A1AA', fontSize: 11 },
  record: { color: '#fff', fontSize: 13, fontWeight: '600', marginRight: 12 },
  pf: { color: '#A1A1AA', fontSize: 11 },
  matchupCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#141414', borderRadius: 8, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
  matchupSide: { flex: 1 },
  matchupTeam: { color: '#fff', fontSize: 14, fontWeight: '600' },
  winner: { color: '#00D2FF' },
  scoreBox: { paddingHorizontal: 16 },
  score: { color: '#fff', fontSize: 16, fontWeight: '800' },
  vs: { color: '#A1A1AA', fontSize: 12 },
});
