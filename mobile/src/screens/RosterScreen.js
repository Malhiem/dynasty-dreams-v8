import React, { useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, TextInput, StyleSheet, SafeAreaView, RefreshControl } from 'react-native';
import api from '../lib/api';
import { useAuth } from '../contexts/AuthContext';

export default function RosterScreen({ navigation }) {
  const { user } = useAuth();
  const [team, setTeam] = useState(null);
  const [roster, setRoster] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchRoster = async () => {
    try {
      const { data: leagues } = await api.get('/leagues?my_leagues=true');
      if (leagues.length > 0) {
        const { data: teams } = await api.get(`/teams?league_id=${leagues[0].id}`);
        const myTeam = teams.find(t => t.owner_id === user?.id);
        if (myTeam) {
          setTeam(myTeam);
          const { data } = await api.get(`/roster/${myTeam.id}`);
          setRoster(data.players || []);
        }
      }
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { fetchRoster(); }, []);

  return (
    <SafeAreaView style={s.container}>
      <View style={s.header}>
        <Text style={s.title}>{team?.name || 'My Roster'}</Text>
        <Text style={s.subtitle}>{roster.length} players</Text>
      </View>
      <FlatList
        data={roster}
        keyExtractor={item => item.player_id}
        renderItem={({ item }) => (
          <View style={s.row}>
            <View style={s.posBadge}><Text style={s.posText}>{item.position}</Text></View>
            <View style={s.info}>
              <Text style={s.name}>{item.name}</Text>
              <Text style={s.meta}>{item.nhl_team} · {item.games_played}GP {item.goals}G {item.assists}A</Text>
            </View>
            <View style={s.fptsCol}>
              <Text style={s.fptsVal}>{item.fantasy_points?.toFixed(1) || '—'}</Text>
              <Text style={s.fptsLabel}>FPTS</Text>
            </View>
          </View>
        )}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={fetchRoster} tintColor="#00D2FF" />}
        ListEmptyComponent={<View style={s.empty}><Text style={s.emptyText}>{loading ? 'Loading...' : 'Empty roster'}</Text></View>}
        contentContainerStyle={s.list}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  header: { padding: 20, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.1)' },
  title: { fontSize: 24, fontWeight: '800', color: '#fff' },
  subtitle: { fontSize: 13, color: '#A1A1AA', marginTop: 4 },
  list: { padding: 8 },
  row: { flexDirection: 'row', alignItems: 'center', padding: 12, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)' },
  posBadge: { width: 36, height: 36, borderRadius: 8, backgroundColor: '#00D2FF20', alignItems: 'center', justifyContent: 'center' },
  posText: { color: '#00D2FF', fontSize: 12, fontWeight: '700' },
  info: { flex: 1, marginLeft: 12 },
  name: { color: '#fff', fontSize: 14, fontWeight: '600' },
  meta: { color: '#A1A1AA', fontSize: 11, marginTop: 2 },
  fptsCol: { alignItems: 'center' },
  fptsVal: { color: '#00D2FF', fontSize: 16, fontWeight: '800' },
  fptsLabel: { color: '#A1A1AA', fontSize: 9, letterSpacing: 1 },
  empty: { alignItems: 'center', paddingTop: 60 },
  emptyText: { color: '#A1A1AA' },
});
