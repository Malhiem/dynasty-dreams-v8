import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, SafeAreaView, RefreshControl } from 'react-native';
import api from '../lib/api';
import { useAuth } from '../contexts/AuthContext';

export default function DashboardScreen({ navigation }) {
  const { user, logout } = useAuth();
  const [leagues, setLeagues] = useState([]);
  const [unread, setUnread] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = async () => {
    try {
      const [l, n] = await Promise.all([
        api.get('/leagues?my_leagues=true'),
        api.get('/notifications/count'),
      ]);
      setLeagues(l.data);
      setUnread(n.data.count);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { fetchData(); }, []);
  const onRefresh = async () => { setRefreshing(true); await fetchData(); setRefreshing(false); };

  const stats = {
    leagues: leagues.length,
    teams: leagues.reduce((a, l) => a + (l.current_teams || 0), 0),
    upcoming: leagues.filter(l => l.status === 'setup').length,
  };

  return (
    <SafeAreaView style={s.container}>
      <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#00D2FF" />}>
        <View style={s.header}>
          <View>
            <Text style={s.greeting}>WELCOME BACK,</Text>
            <Text style={s.name}>{user?.name?.toUpperCase()}</Text>
          </View>
          <TouchableOpacity style={s.bellBtn} onPress={() => navigation.navigate('Notifications')}>
            <Text style={s.bellIcon}>🔔</Text>
            {unread > 0 && <View style={s.badge}><Text style={s.badgeText}>{unread}</Text></View>}
          </TouchableOpacity>
        </View>

        <View style={s.statsRow}>
          {[{ label: 'Leagues', value: stats.leagues }, { label: 'Teams', value: stats.teams }, { label: 'Upcoming', value: stats.upcoming }].map(st => (
            <View key={st.label} style={s.statCard}>
              <Text style={s.statValue}>{st.value}</Text>
              <Text style={s.statLabel}>{st.label}</Text>
            </View>
          ))}
        </View>

        <Text style={s.sectionTitle}>MY LEAGUES</Text>
        {leagues.length === 0 ? (
          <View style={s.emptyCard}><Text style={s.emptyText}>No leagues yet</Text></View>
        ) : leagues.map(l => (
          <TouchableOpacity key={l.id} style={s.leagueCard} onPress={() => navigation.navigate('LeagueDetail', { leagueId: l.id })}>
            <View style={s.leagueRow}>
              <View>
                <Text style={s.leagueName}>{l.name}</Text>
                <Text style={s.leagueMeta}>{l.sport?.toUpperCase()} · {l.format?.replace('_', ' ')} · {l.scoring_format?.replace('_', ' ')}</Text>
              </View>
              <View style={s.teamsCountBadge}><Text style={s.teamsCountText}>{l.current_teams}/{l.max_teams}</Text></View>
            </View>
          </TouchableOpacity>
        ))}

        <TouchableOpacity style={s.logoutBtn} onPress={logout}>
          <Text style={s.logoutText}>Sign Out</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 20 },
  greeting: { fontSize: 14, color: '#A1A1AA', letterSpacing: 1 },
  name: { fontSize: 28, fontWeight: '900', color: '#fff' },
  bellBtn: { position: 'relative', padding: 8 },
  bellIcon: { fontSize: 24 },
  badge: { position: 'absolute', top: 2, right: 2, backgroundColor: '#FF3B30', borderRadius: 10, width: 20, height: 20, alignItems: 'center', justifyContent: 'center' },
  badgeText: { color: '#fff', fontSize: 10, fontWeight: '700' },
  statsRow: { flexDirection: 'row', paddingHorizontal: 16, gap: 12, marginBottom: 24 },
  statCard: { flex: 1, backgroundColor: '#141414', borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: 16, alignItems: 'center' },
  statValue: { fontSize: 32, fontWeight: '900', color: '#fff' },
  statLabel: { fontSize: 11, color: '#A1A1AA', textTransform: 'uppercase', letterSpacing: 1, marginTop: 4 },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: '#fff', paddingHorizontal: 20, marginBottom: 12, letterSpacing: 0.5 },
  emptyCard: { margin: 16, backgroundColor: '#141414', borderRadius: 8, padding: 40, alignItems: 'center' },
  emptyText: { color: '#A1A1AA' },
  leagueCard: { marginHorizontal: 16, marginBottom: 8, backgroundColor: '#141414', borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: 16 },
  leagueRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  leagueName: { fontSize: 16, fontWeight: '700', color: '#fff' },
  leagueMeta: { fontSize: 12, color: '#A1A1AA', marginTop: 4 },
  teamsCountBadge: { backgroundColor: '#00D2FF20', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  teamsCountText: { color: '#00D2FF', fontSize: 12, fontWeight: '700' },
  logoutBtn: { margin: 20, padding: 14, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)', borderRadius: 8, alignItems: 'center' },
  logoutText: { color: '#A1A1AA', fontSize: 14 },
});
