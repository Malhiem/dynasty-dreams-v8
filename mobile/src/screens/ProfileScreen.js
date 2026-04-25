import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, SafeAreaView, RefreshControl, TouchableOpacity } from 'react-native';
import api from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { useGlobalSocketEvent } from '../hooks/useSocket';

const TROPHY_PALETTES = {
  championship: { bg: '#fbbf2422', border: '#fbbf2466', text: '#fbbf24', icon: '🏆', label: 'CHAMPIONSHIP' },
  conference: { bg: '#a78bfa22', border: '#a78bfa55', text: '#c4b5fd', icon: '🥇', label: 'CONFERENCE' },
  division: { bg: '#38bdf822', border: '#38bdf855', text: '#7dd3fc', icon: '🏅', label: 'DIVISION' },
  consolation: { bg: '#34d39922', border: '#34d39955', text: '#6ee7b7', icon: '🎖', label: 'CONSOLATION' },
  lead: { bg: '#fbbf2422', border: '#fbbf2466', text: '#fbbf24', icon: '🥇', label: 'CURRENT 1ST' },
  top3: { bg: '#38bdf822', border: '#38bdf855', text: '#7dd3fc', icon: '⭐', label: 'TOP 3' },
};

export default function ProfileScreen({ route, navigation }) {
  const { user } = useAuth();
  const username = route?.params?.username || user?.username;
  const [profile, setProfile] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!username) return;
    try {
      const { data } = await api.get(`/u/${username}`);
      setProfile(data);
      setError('');
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to load profile');
    }
  }, [username]);

  useEffect(() => { load(); }, [load]);

  // Live champion broadcasts re-fetch profile to update championship counts
  useGlobalSocketEvent('championship_crowned', () => { load(); });
  useGlobalSocketEvent('consolation_crowned', () => { load(); });
  useGlobalSocketEvent('conference_crowned', () => { load(); });
  useGlobalSocketEvent('division_crowned', () => { load(); });

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  if (error) {
    return (
      <SafeAreaView style={s.container}>
        <View style={s.center}><Text style={s.errorText}>{error}</Text></View>
      </SafeAreaView>
    );
  }
  if (!profile) {
    return (
      <SafeAreaView style={s.container}>
        <View style={s.center}><Text style={s.dim}>Loading…</Text></View>
      </SafeAreaView>
    );
  }

  const winRate = profile.stats.total_wins + profile.stats.total_losses > 0
    ? Math.round((profile.stats.total_wins / (profile.stats.total_wins + profile.stats.total_losses)) * 100)
    : 0;

  return (
    <SafeAreaView style={s.container}>
      <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#00D2FF" />}>
        <View style={s.header}>
          <View style={s.avatar}><Text style={s.avatarText}>{profile.display_name?.[0]?.toUpperCase() || '?'}</Text></View>
          <Text style={s.username}>{profile.display_name?.toUpperCase()}</Text>
          <Text style={s.handle}>@{profile.username}</Text>
          <View style={s.levelRow}>
            <View style={s.levelBadge}><Text style={s.levelText}>LEVEL {profile.level}</Text></View>
            <Text style={s.title}>{profile.title}</Text>
          </View>
          <View style={s.xpBar}>
            <View style={[s.xpFill, { width: `${Math.min(100, profile.progress_pct)}%` }]} />
          </View>
          <Text style={s.xpText}>{profile.xp_in_level} / {profile.xp_required_for_next} XP</Text>
        </View>

        <View style={s.statsRow}>
          {[
            { label: 'Leagues', value: profile.stats.leagues_joined },
            { label: 'Record', value: `${profile.stats.total_wins}-${profile.stats.total_losses}-${profile.stats.total_ties}` },
            { label: 'Win %', value: `${winRate}%` },
            { label: 'Points', value: profile.stats.total_points.toFixed(0) },
          ].map(st => (
            <View key={st.label} style={s.statCard}>
              <Text style={s.statValue}>{st.value}</Text>
              <Text style={s.statLabel}>{st.label}</Text>
            </View>
          ))}
        </View>

        {(profile.stats.championships_won > 0
          || profile.stats.conference_titles > 0
          || profile.stats.division_titles > 0
          || profile.stats.consolations_won > 0
          || profile.stats.playoff_appearances > 0) && (
          <>
            <Text style={s.sectionTitle}>CAREER CHAMPIONSHIPS</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.careerScroll}>
              {[
                { label: 'Championships', value: profile.stats.championships_won, palette: TROPHY_PALETTES.championship },
                { label: 'Conference', value: profile.stats.conference_titles, palette: TROPHY_PALETTES.conference },
                { label: 'Division', value: profile.stats.division_titles, palette: TROPHY_PALETTES.division },
                { label: 'Consolations', value: profile.stats.consolations_won, palette: TROPHY_PALETTES.consolation },
                { label: 'Playoffs', value: profile.stats.playoff_appearances, palette: TROPHY_PALETTES.top3 },
              ].map(card => (
                <View
                  key={card.label}
                  style={[s.careerCard, { backgroundColor: card.palette.bg, borderColor: card.palette.border }]}
                  testID={`profile-stat-${card.label.toLowerCase()}`}
                >
                  <Text style={s.careerIcon}>{card.palette.icon}</Text>
                  <Text style={[s.careerValue, { color: card.palette.text }]}>{card.value}</Text>
                  <Text style={s.careerLabel}>{card.label.toUpperCase()}</Text>
                </View>
              ))}
            </ScrollView>
          </>
        )}

        {profile.trophies.length > 0 && (
          <>
            <Text style={s.sectionTitle}>TROPHY CASE ({profile.trophies.length})</Text>
            <View style={s.trophyGrid}>
              {profile.trophies.map((t, i) => {
                const palette = TROPHY_PALETTES[t.type] || TROPHY_PALETTES.top3;
                return (
                  <TouchableOpacity
                    key={`${t.league_id}-${i}`}
                    style={[s.trophy, { backgroundColor: palette.bg, borderColor: palette.border }]}
                    testID={`profile-trophy-${t.type}-${i}`}
                  >
                    <Text style={s.trophyIcon}>{palette.icon}</Text>
                    <Text style={[s.trophyLabel, { color: palette.text }]}>{palette.label}</Text>
                    <Text style={s.trophyTeam}>{t.team_name}</Text>
                    <Text style={s.trophyLeague}>{t.league_name}</Text>
                    {t.earned_at && (
                      <Text style={s.trophyDate}>Earned {new Date(t.earned_at).toLocaleDateString()}</Text>
                    )}
                  </TouchableOpacity>
                );
              })}
            </View>
          </>
        )}

        <Text style={s.sectionTitle}>MY TEAMS</Text>
        {profile.teams.map(team => (
          <View key={team.team_id} style={s.teamCard}>
            <View style={s.teamRow}>
              <View style={{ flex: 1 }}>
                <Text style={s.teamName}>{team.team_name}</Text>
                <Text style={s.teamMeta}>{team.league_name}</Text>
              </View>
              <View style={s.rankBadge}><Text style={s.rankText}>#{team.rank || '-'}/{team.total_teams}</Text></View>
            </View>
            <View style={s.teamStatsRow}>
              <Text style={s.teamStat}>{team.wins}-{team.losses}-{team.ties}</Text>
              <Text style={s.teamStatDim}>·</Text>
              <Text style={s.teamStat}>{team.points_for?.toFixed(1) || 0} PF</Text>
            </View>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 },
  errorText: { color: '#FF3B30', fontSize: 14, textAlign: 'center' },
  dim: { color: '#A1A1AA', fontSize: 14 },
  header: { padding: 24, alignItems: 'center', backgroundColor: '#141414', borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.08)' },
  avatar: { width: 80, height: 80, borderRadius: 40, backgroundColor: '#00D2FF20', alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
  avatarText: { color: '#00D2FF', fontSize: 36, fontWeight: '900' },
  username: { color: '#fff', fontSize: 24, fontWeight: '900', letterSpacing: -0.5 },
  handle: { color: '#A1A1AA', fontSize: 13, marginTop: 2, marginBottom: 12 },
  levelRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  levelBadge: { backgroundColor: '#00D2FF', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 4 },
  levelText: { color: '#000', fontSize: 11, fontWeight: '900', letterSpacing: 0.5 },
  title: { color: '#A1A1AA', fontSize: 12, marginLeft: 4 },
  xpBar: { width: '100%', height: 4, backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: 2, marginTop: 12, overflow: 'hidden' },
  xpFill: { height: '100%', backgroundColor: '#00D2FF' },
  xpText: { color: '#A1A1AA', fontSize: 10, marginTop: 4 },
  statsRow: { flexDirection: 'row', padding: 16, gap: 8 },
  statCard: { flex: 1, backgroundColor: '#141414', borderRadius: 8, padding: 12, alignItems: 'center', borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)' },
  statValue: { color: '#fff', fontSize: 18, fontWeight: '900' },
  statLabel: { color: '#A1A1AA', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 2 },
  sectionTitle: { color: '#fff', fontSize: 14, fontWeight: '700', paddingHorizontal: 16, marginTop: 16, marginBottom: 8, letterSpacing: 0.5 },
  careerScroll: { paddingHorizontal: 16, gap: 8 },
  careerCard: { width: 110, padding: 12, borderRadius: 12, borderWidth: 1, alignItems: 'flex-start' },
  careerIcon: { fontSize: 22 },
  careerValue: { fontSize: 28, fontWeight: '900', marginTop: 4 },
  careerLabel: { color: 'rgba(255,255,255,0.7)', fontSize: 9, fontWeight: '700', letterSpacing: 0.5, marginTop: 2 },
  trophyGrid: { paddingHorizontal: 16, flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  trophy: { width: '48%', padding: 12, borderRadius: 12, borderWidth: 1, marginBottom: 8 },
  trophyIcon: { fontSize: 22, marginBottom: 4 },
  trophyLabel: { fontSize: 10, fontWeight: '900', letterSpacing: 0.5, marginBottom: 4 },
  trophyTeam: { color: '#fff', fontSize: 14, fontWeight: '700' },
  trophyLeague: { color: '#A1A1AA', fontSize: 11, marginTop: 1 },
  trophyDate: { color: '#52525B', fontSize: 9, marginTop: 4 },
  teamCard: { marginHorizontal: 16, marginBottom: 8, backgroundColor: '#141414', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)' },
  teamRow: { flexDirection: 'row', alignItems: 'center' },
  teamName: { color: '#fff', fontSize: 14, fontWeight: '700' },
  teamMeta: { color: '#A1A1AA', fontSize: 11, marginTop: 2 },
  rankBadge: { backgroundColor: '#00D2FF20', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  rankText: { color: '#00D2FF', fontSize: 11, fontWeight: '700' },
  teamStatsRow: { flexDirection: 'row', gap: 6, marginTop: 6 },
  teamStat: { color: '#A1A1AA', fontSize: 11 },
  teamStatDim: { color: '#52525B', fontSize: 11 },
});
