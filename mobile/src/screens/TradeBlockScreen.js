import React, { useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, SafeAreaView, RefreshControl } from 'react-native';
import api from '../lib/api';

export default function TradeBlockScreen() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try { const { data } = await api.get('/trade-block'); setItems(data); } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, []);

  return (
    <SafeAreaView style={s.container}>
      <FlatList
        data={items}
        keyExtractor={item => item._id}
        ListHeaderComponent={<View style={s.header}><Text style={s.title}>TRADE BLOCK</Text><Text style={s.subtitle}>{items.length} players available</Text></View>}
        renderItem={({ item }) => (
          <View style={s.card}>
            <View style={s.row}>
              <View style={s.avatar}><Text style={s.avatarText}>{item.nhl_team || item.position?.[0]}</Text></View>
              <View style={s.info}>
                <Text style={s.name}>{item.name}</Text>
                <Text style={s.meta}>{item.position} · {item.nhl_team}{item.points > 0 ? ` · ${item.points} pts` : ''}</Text>
                <View style={s.tagsRow}>{(item.looking_for || []).map((t, i) => <View key={i} style={s.tag}><Text style={s.tagText}>{t}</Text></View>)}</View>
              </View>
              <Text style={s.owner}>{item.owner_name}</Text>
            </View>
          </View>
        )}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={fetchData} tintColor="#00D2FF" />}
        contentContainerStyle={s.list}
        ListEmptyComponent={<View style={s.empty}><Text style={s.emptyText}>{loading ? 'Loading...' : 'No items on trade block'}</Text></View>}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  header: { padding: 20 },
  title: { fontSize: 22, fontWeight: '800', color: '#fff' },
  subtitle: { fontSize: 13, color: '#A1A1AA', marginTop: 4 },
  list: { paddingBottom: 20 },
  card: { marginHorizontal: 16, marginBottom: 8, backgroundColor: '#141414', borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: 14 },
  row: { flexDirection: 'row', alignItems: 'flex-start' },
  avatar: { width: 44, height: 44, borderRadius: 10, backgroundColor: '#1A1A1A', alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: '#00D2FF', fontSize: 12, fontWeight: '800' },
  info: { flex: 1, marginLeft: 12 },
  name: { color: '#fff', fontSize: 15, fontWeight: '700' },
  meta: { color: '#A1A1AA', fontSize: 11, marginTop: 3 },
  tagsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 },
  tag: { backgroundColor: '#1A1A1A', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4 },
  tagText: { color: '#A1A1AA', fontSize: 10 },
  owner: { color: '#A1A1AA', fontSize: 11 },
  empty: { alignItems: 'center', paddingTop: 60 },
  emptyText: { color: '#A1A1AA' },
});
