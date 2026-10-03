import React, { useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, SafeAreaView, RefreshControl } from 'react-native';
import api from '../lib/api';
import { useAuth } from '../contexts/AuthContext';

export default function LeaguesScreen({ route, navigation }) {
  const { user } = useAuth();
  const [leagues, setLeagues] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchLeagues = async () => {
    try {
      const { data } = await api.get('/leagues');
      setLeagues(data);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { fetchLeagues(); }, []);

  return (
    <SafeAreaView style={s.container}>
      <FlatList
        data={leagues}
        keyExtractor={item => item.id}
        renderItem={({ item }) => (
          <TouchableOpacity style={s.card} onPress={() => navigation.navigate('StandingsDetail', { leagueId: item.id })}>
            <View style={s.row}>
              <View style={s.sportBadge}><Text style={s.sportText}>{(item.sport || 'nhl').toUpperCase()}</Text></View>
              <View style={s.info}>
                <Text style={s.name}>{item.name}</Text>
                <Text style={s.meta}>{item.format?.replace('_', ' ')} · {item.scoring_format?.replace('_', ' ')}</Text>
              </View>
              <View>
                <Text style={s.teams}>{item.current_teams}/{item.max_teams}</Text>
                <Text style={s.teamsLabel}>teams</Text>
              </View>
            </View>
          </TouchableOpacity>
        )}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={fetchLeagues} tintColor="#00D2FF" />}
        contentContainerStyle={s.list}
        ListHeaderComponent={<Text style={s.header}>ALL LEAGUES</Text>}
        ListEmptyComponent={<View style={s.empty}><Text style={s.emptyText}>No leagues</Text></View>}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  list: { padding: 16 },
  header: { fontSize: 18, fontWeight: '800', color: '#fff', marginBottom: 16, letterSpacing: 0.5 },
  card: { backgroundColor: '#141414', borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: 14, marginBottom: 8 },
  row: { flexDirection: 'row', alignItems: 'center' },
  sportBadge: { width: 40, height: 40, borderRadius: 8, backgroundColor: '#00D2FF20', alignItems: 'center', justifyContent: 'center' },
  sportText: { color: '#00D2FF', fontSize: 11, fontWeight: '800' },
  info: { flex: 1, marginLeft: 12 },
  name: { color: '#fff', fontSize: 15, fontWeight: '700' },
  meta: { color: '#A1A1AA', fontSize: 11, marginTop: 3, textTransform: 'uppercase' },
  teams: { color: '#00D2FF', fontSize: 16, fontWeight: '800', textAlign: 'right' },
  teamsLabel: { color: '#A1A1AA', fontSize: 9, textAlign: 'right', textTransform: 'uppercase' },
  empty: { alignItems: 'center', paddingTop: 60 },
  emptyText: { color: '#A1A1AA' },
});
