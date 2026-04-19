import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, StyleSheet, SafeAreaView, RefreshControl } from 'react-native';
import api from '../lib/api';
import { useAuth } from '../contexts/AuthContext';

export default function SalaryCapScreen() {
  const { user } = useAuth();
  const [overview, setOverview] = useState(null);
  const [contracts, setContracts] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const { data: leagues } = await api.get('/leagues?my_leagues=true');
      if (leagues.length > 0) {
        const lid = leagues[0].id;
        const [o, c] = await Promise.all([api.get(`/salary-cap/${lid}`), api.get(`/contracts?league_id=${lid}`)]);
        setOverview(o.data);
        setContracts(c.data.filter(ct => ct.status === 'active'));
      }
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, []);
  const cap = overview?.salary_cap || 82500000;

  return (
    <SafeAreaView style={s.container}>
      <ScrollView refreshControl={<RefreshControl refreshing={loading} onRefresh={fetchData} tintColor="#00D2FF" />}>
        <View style={s.header}><Text style={s.title}>SALARY CAP</Text><Text style={s.capValue}>${(cap / 1000000).toFixed(1)}M</Text></View>

        {(overview?.teams || []).map(team => (
          <View key={team.team_id} style={s.teamCard}>
            <View style={s.teamRow}>
              <Text style={s.teamName}>{team.team_name}</Text>
              <Text style={[s.capPct, team.cap_pct > 90 ? s.danger : team.cap_pct > 70 ? s.warning : s.success]}>{team.cap_pct}%</Text>
            </View>
            <View style={s.barBg}><View style={[s.barFill, { width: `${Math.min(team.cap_pct, 100)}%` }]} /></View>
            <View style={s.teamMeta}>
              <Text style={s.metaText}>Used: ${(team.cap_used || 0).toLocaleString()}</Text>
              <Text style={[s.metaText, s.success]}>Free: ${(team.cap_remaining || 0).toLocaleString()}</Text>
            </View>
          </View>
        ))}

        <Text style={s.sectionTitle}>ACTIVE CONTRACTS ({contracts.length})</Text>
        {contracts.map(c => (
          <View key={c._id} style={s.contractRow}>
            <View style={s.contractInfo}>
              <Text style={s.contractName}>{c.player_name}</Text>
              <Text style={s.contractMeta}>{c.player_position} · {c.team_name} · {c.years}yr · FA {c.free_agency_year}</Text>
              <View style={s.clauseRow}>
                {c.no_trade_clause && <View style={s.clauseBadge}><Text style={s.clauseText}>NTC</Text></View>}
                {c.no_move_clause && <View style={[s.clauseBadge, s.clauseDanger]}><Text style={[s.clauseText, s.clauseDangerText]}>NMC</Text></View>}
                <View style={[s.statusBadge, c.player_status === 'ufa' ? s.statusDanger : c.player_status === 'rfa' ? s.statusWarning : s.statusSuccess]}>
                  <Text style={s.statusText}>{c.player_status?.toUpperCase()}</Text>
                </View>
              </View>
            </View>
            <Text style={s.aav}>${(c.aav || 0).toLocaleString()}</Text>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 20 },
  title: { fontSize: 22, fontWeight: '800', color: '#fff' },
  capValue: { fontSize: 22, fontWeight: '800', color: '#00D2FF' },
  teamCard: { marginHorizontal: 16, marginBottom: 8, backgroundColor: '#141414', borderRadius: 8, padding: 14, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
  teamRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  teamName: { color: '#fff', fontSize: 14, fontWeight: '600' },
  capPct: { fontSize: 14, fontWeight: '700' },
  danger: { color: '#FF3B30' },
  warning: { color: '#FF9F0A' },
  success: { color: '#34C759' },
  barBg: { height: 6, backgroundColor: '#1A1A1A', borderRadius: 3, overflow: 'hidden' },
  barFill: { height: '100%', backgroundColor: '#00D2FF', borderRadius: 3 },
  teamMeta: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
  metaText: { color: '#A1A1AA', fontSize: 11 },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: '#A1A1AA', padding: 16, paddingBottom: 8, letterSpacing: 1 },
  contractRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)' },
  contractInfo: { flex: 1 },
  contractName: { color: '#fff', fontSize: 14, fontWeight: '600' },
  contractMeta: { color: '#A1A1AA', fontSize: 11, marginTop: 3 },
  clauseRow: { flexDirection: 'row', gap: 6, marginTop: 6 },
  clauseBadge: { backgroundColor: '#FF9F0A20', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  clauseText: { color: '#FF9F0A', fontSize: 9, fontWeight: '700' },
  clauseDanger: { backgroundColor: '#FF3B3020' },
  clauseDangerText: { color: '#FF3B30' },
  statusBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  statusDanger: { backgroundColor: '#FF3B3020' },
  statusWarning: { backgroundColor: '#FF9F0A20' },
  statusSuccess: { backgroundColor: '#34C75920' },
  statusText: { fontSize: 9, fontWeight: '700', color: '#34C759' },
  aav: { color: '#00D2FF', fontSize: 16, fontWeight: '800' },
});
