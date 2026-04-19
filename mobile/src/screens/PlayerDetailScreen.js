import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, StyleSheet, SafeAreaView } from 'react-native';
import api from '../lib/api';

export default function PlayerDetailScreen({ route }) {
  const { playerId } = route.params;
  const [player, setPlayer] = useState(null);

  useEffect(() => {
    api.get(`/players/${playerId}`).then(r => setPlayer(r.data)).catch(console.error);
  }, [playerId]);

  if (!player) return <SafeAreaView style={s.container}><Text style={s.loading}>Loading...</Text></SafeAreaView>;

  const isGoalie = player.position === 'G';
  const fpts = isGoalie ? ((player.wins||0)*5 + (player.saves||0)*0.2 - (player.goals_against||0)) : ((player.goals||0)*3 + (player.assists||0)*2 + (player.plus_minus||0));

  return (
    <SafeAreaView style={s.container}>
      <ScrollView contentContainerStyle={s.scroll}>
        <View style={s.headerCard}>
          <View style={s.teamBadge}><Text style={s.teamText}>{player.team || '?'}</Text></View>
          <Text style={s.name}>{player.name}</Text>
          <Text style={s.meta}>{player.position} · {player.team_name || player.team}</Text>
          <View style={s.fptsRow}>
            <Text style={s.fptsLabel}>Fantasy Points</Text>
            <Text style={s.fptsValue}>{fpts.toFixed(1)}</Text>
          </View>
        </View>

        <View style={s.statsGrid}>
          {isGoalie ? [
            { l: 'Wins', v: player.wins||0 }, { l: 'Losses', v: player.losses||0 },
            { l: 'SV%', v: `${(player.save_pct||0).toFixed(1)}%` }, { l: 'GAA', v: (player.goals_against_avg||0).toFixed(2) },
            { l: 'Shutouts', v: player.shutouts||0 }, { l: 'GP', v: player.games_played||0 },
          ].map(st => <StatBox key={st.l} {...st} />) : [
            { l: 'Goals', v: player.goals||0 }, { l: 'Assists', v: player.assists||0 },
            { l: 'Points', v: player.points||0 }, { l: '+/-', v: player.plus_minus||0 },
            { l: 'PPG', v: player.power_play_goals||0 }, { l: 'PPP', v: player.power_play_points||0 },
            { l: 'SOG', v: player.shots||0 }, { l: 'PIM', v: player.penalty_minutes||0 },
            { l: 'GWG', v: player.game_winning_goals||0 }, { l: 'SHG', v: player.short_handed_goals||0 },
            { l: 'SH%', v: `${(player.shooting_pct||0).toFixed(1)}%` }, { l: 'GP', v: player.games_played||0 },
          ].map(st => <StatBox key={st.l} {...st} />)}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function StatBox({ l, v }) {
  return (
    <View style={s.statBox}>
      <Text style={s.statValue}>{v}</Text>
      <Text style={s.statLabel}>{l}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  loading: { color: '#A1A1AA', textAlign: 'center', marginTop: 100 },
  scroll: { padding: 16 },
  headerCard: { backgroundColor: '#141414', borderRadius: 12, padding: 24, alignItems: 'center', marginBottom: 16, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
  teamBadge: { width: 64, height: 64, borderRadius: 16, backgroundColor: '#1A1A1A', alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
  teamText: { color: '#00D2FF', fontSize: 18, fontWeight: '800' },
  name: { fontSize: 24, fontWeight: '800', color: '#fff', marginBottom: 4 },
  meta: { fontSize: 14, color: '#A1A1AA' },
  fptsRow: { marginTop: 16, alignItems: 'center' },
  fptsLabel: { fontSize: 11, color: '#A1A1AA', textTransform: 'uppercase', letterSpacing: 1 },
  fptsValue: { fontSize: 36, fontWeight: '900', color: '#00D2FF' },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  statBox: { width: '31%', backgroundColor: '#141414', borderRadius: 8, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
  statValue: { fontSize: 20, fontWeight: '800', color: '#fff' },
  statLabel: { fontSize: 10, color: '#A1A1AA', textTransform: 'uppercase', letterSpacing: 1, marginTop: 4 },
});
