import React, { useState, useEffect } from 'react';
import { View, Text, FlatList, TextInput, TouchableOpacity, StyleSheet, SafeAreaView, RefreshControl } from 'react-native';
import api from '../lib/api';

export default function PlayersScreen({ navigation }) {
  const [players, setPlayers] = useState([]);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const fetchPlayers = async (p = 1, s = search) => {
    try {
      const params = new URLSearchParams({ page: p.toString(), limit: '25' });
      if (s) params.append('search', s);
      const { data } = await api.get(`/players?${params}`);
      setPlayers(p === 1 ? data.players : [...players, ...data.players]);
      setTotal(data.total);
      setPage(p);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { fetchPlayers(1); }, []);
  useEffect(() => { const t = setTimeout(() => fetchPlayers(1, search), 400); return () => clearTimeout(t); }, [search]);

  return (
    <SafeAreaView style={s.container}>
      <View style={s.searchBar}>
        <TextInput style={s.searchInput} placeholder="Search players or teams..." placeholderTextColor="#52525B" value={search} onChangeText={setSearch} />
      </View>
      <FlatList
        data={players}
        keyExtractor={item => item._id}
        renderItem={({ item }) => (
          <TouchableOpacity style={s.row} onPress={() => navigation.navigate('PlayerDetail', { playerId: item._id })}>
            <View style={[s.posBadge, { backgroundColor: item.position === 'G' ? '#7C3AED40' : '#00D2FF20' }]}>
              <Text style={[s.posText, { color: item.position === 'G' ? '#A78BFA' : '#00D2FF' }]}>{item.position}</Text>
            </View>
            <View style={s.info}>
              <Text style={s.name}>{item.name}</Text>
              <Text style={s.meta}>{item.team} · {item.games_played || 0}GP</Text>
            </View>
            <View style={s.stats}>
              <Text style={s.pts}>{item.points || 0}</Text>
              <Text style={s.ptsLabel}>PTS</Text>
            </View>
          </TouchableOpacity>
        )}
        onEndReached={() => { if (players.length < total) fetchPlayers(page + 1); }}
        onEndReachedThreshold={0.3}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={() => fetchPlayers(1)} tintColor="#00D2FF" />}
        contentContainerStyle={s.list}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  searchBar: { padding: 12, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.1)' },
  searchInput: { backgroundColor: '#141414', borderRadius: 8, padding: 12, color: '#fff', fontSize: 14 },
  list: { padding: 8 },
  row: { flexDirection: 'row', alignItems: 'center', padding: 12, marginBottom: 2, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)' },
  posBadge: { width: 36, height: 36, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  posText: { fontSize: 12, fontWeight: '700' },
  info: { flex: 1, marginLeft: 12 },
  name: { color: '#fff', fontSize: 14, fontWeight: '600' },
  meta: { color: '#A1A1AA', fontSize: 11, marginTop: 2 },
  stats: { alignItems: 'center' },
  pts: { color: '#00D2FF', fontSize: 18, fontWeight: '800' },
  ptsLabel: { color: '#A1A1AA', fontSize: 9, letterSpacing: 1 },
});
