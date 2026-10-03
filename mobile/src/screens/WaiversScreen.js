import React, { useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, SafeAreaView, RefreshControl } from 'react-native';
import api from '../lib/api';
import { useAuth } from '../contexts/AuthContext';

export default function WaiversScreen() {
  const { user } = useAuth();
  const [players, setPlayers] = useState([]);
  const [budget, setBudget] = useState({ total_budget: 100, spent: 0, remaining: 100 });
  const [claims, setClaims] = useState([]);
  const [leagueId, setLeagueId] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const init = async () => {
      try {
        const { data: leagues } = await api.get('/leagues?my_leagues=true');
        if (leagues.length > 0) {
          const lid = leagues[0].id;
          setLeagueId(lid);
          const [p, b, c] = await Promise.all([
            api.get(`/waivers/available?limit=20`),
            api.get(`/waivers/budget?league_id=${lid}`),
            api.get(`/waivers/claims?my_claims=true&league_id=${lid}`),
          ]);
          setPlayers(p.data.players || []);
          setBudget(b.data);
          setClaims(c.data.filter(cl => cl.status === 'pending'));
        }
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    init();
  }, []);

  return (
    <SafeAreaView style={s.container}>
      <View style={s.budgetBar}>
        <View style={s.budgetItem}><Text style={s.budgetLabel}>FAAB Budget</Text><Text style={s.budgetValue}>${budget.remaining}</Text></View>
        <View style={s.budgetItem}><Text style={s.budgetLabel}>Spent</Text><Text style={s.budgetValueDim}>${budget.spent}</Text></View>
        <View style={s.budgetItem}><Text style={s.budgetLabel}>Claims</Text><Text style={s.budgetValueDim}>{claims.length}</Text></View>
      </View>
      <FlatList
        data={players}
        keyExtractor={item => item.id}
        renderItem={({ item }) => (
          <View style={s.row}>
            <View style={s.posBadge}><Text style={s.posText}>{item.position}</Text></View>
            <View style={s.info}>
              <Text style={s.name}>{item.name}</Text>
              <Text style={s.meta}>{item.team} · {item.points}P · {item.goals}G {item.assists}A</Text>
            </View>
            <TouchableOpacity style={s.claimBtn}>
              <Text style={s.claimText}>Claim</Text>
            </TouchableOpacity>
          </View>
        )}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={() => {}} tintColor="#00D2FF" />}
        ListHeaderComponent={<Text style={s.sectionTitle}>AVAILABLE PLAYERS</Text>}
        contentContainerStyle={s.list}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  budgetBar: { flexDirection: 'row', padding: 16, gap: 12, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.1)' },
  budgetItem: { flex: 1, backgroundColor: '#141414', borderRadius: 8, padding: 12, alignItems: 'center' },
  budgetLabel: { fontSize: 9, color: '#A1A1AA', textTransform: 'uppercase', letterSpacing: 1 },
  budgetValue: { fontSize: 22, fontWeight: '800', color: '#00D2FF', marginTop: 4 },
  budgetValueDim: { fontSize: 22, fontWeight: '800', color: '#fff', marginTop: 4 },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: '#A1A1AA', paddingHorizontal: 16, paddingVertical: 12, letterSpacing: 1 },
  list: { paddingBottom: 20 },
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)' },
  posBadge: { width: 36, height: 36, borderRadius: 8, backgroundColor: '#00D2FF20', alignItems: 'center', justifyContent: 'center' },
  posText: { color: '#00D2FF', fontSize: 12, fontWeight: '700' },
  info: { flex: 1, marginLeft: 12 },
  name: { color: '#fff', fontSize: 14, fontWeight: '600' },
  meta: { color: '#A1A1AA', fontSize: 11, marginTop: 2 },
  claimBtn: { backgroundColor: '#00D2FF', paddingHorizontal: 14, paddingVertical: 6, borderRadius: 6 },
  claimText: { color: '#000', fontSize: 12, fontWeight: '700' },
});
