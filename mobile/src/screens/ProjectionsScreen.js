/**
 * ProjectionsScreen — Pro player projection viewer (mobile parity with the
 * Projections tab on PlayerDetailPage). Shows ROS + next-week cards built
 * from /players/{id}/projections.
 *
 * Pro-paywalled at the API layer when the league has analyzer constraints
 * configured. We default to displaying the result; if the underlying
 * endpoint returns a 402 the screen surfaces an upgrade upsell.
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, SafeAreaView, ScrollView, TextInput,
  TouchableOpacity, ActivityIndicator, Modal, Alert,
} from 'react-native';
import api from '../lib/api';

const COL = {
  bg: '#0A0A0A', card: '#141414', border: 'rgba(255,255,255,0.08)',
  text: '#fff', sub: '#A1A1AA', muted: '#71717A',
  cyan: '#00D2FF', gold: '#FFB020',
};

function PlayerSearch({ onPick }) {
  const [q, setQ] = useState('');
  const [opts, setOpts] = useState([]);
  useEffect(() => {
    if (!q || q.length < 2) { setOpts([]); return; }
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get(`/players?search=${encodeURIComponent(q)}&limit=8`);
        setOpts(data?.players || []);
      } catch { setOpts([]); }
    }, 300);
    return () => clearTimeout(t);
  }, [q]);
  return (
    <View style={s.searchBlock}>
      <TextInput
        testID="proj-search-input"
        value={q}
        onChangeText={setQ}
        placeholder="Search player…"
        placeholderTextColor={COL.muted}
        style={s.input}
      />
      {opts.map(p => (
        <TouchableOpacity
          key={p._id}
          testID={`proj-search-result-${p._id}`}
          onPress={() => { onPick(p); setQ(''); setOpts([]); }}
          style={s.resultRow}
        >
          <Text style={s.resultName}>{p.name}</Text>
          <Text style={s.resultMeta}>{p.position} · {p.team}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

export default function ProjectionsScreen({ route }) {
  const initialPlayer = route?.params?.player || null;
  const leagueId = route?.params?.leagueId || null;
  const [player, setPlayer] = useState(initialPlayer);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [paywall, setPaywall] = useState(false);

  const fetchProj = useCallback(async (pid) => {
    if (!pid) return;
    setLoading(true);
    setData(null);
    try {
      const params = leagueId ? `?league_id=${leagueId}` : '';
      const { data: d } = await api.get(`/players/${pid}/projections${params}`);
      setData(d);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 402 && detail?.code === 'upgrade_required') {
        setPaywall(true);
      } else {
        Alert.alert('Could not load projections', typeof detail === 'string' ? detail : 'Unknown error');
      }
    } finally { setLoading(false); }
  }, [leagueId]);

  useEffect(() => { if (player?._id) fetchProj(player._id); }, [player, fetchProj]);

  return (
    <SafeAreaView style={s.container} testID="projections-screen">
      <ScrollView contentContainerStyle={s.scroll}>
        <Text style={s.title}>📈 Player Projections</Text>
        <Text style={s.sub}>Rest-of-season + next-week FPTS forecasts using a 60/40 blend of season + last-14-day momentum.</Text>

        <PlayerSearch onPick={(p) => setPlayer(p)} />

        {player && (
          <View style={s.card} testID="proj-player-header">
            <Text style={s.playerName}>{player.name}</Text>
            <Text style={s.playerMeta}>{player.position} · {player.team}</Text>
          </View>
        )}

        {loading && <ActivityIndicator size="large" color={COL.cyan} style={{ marginTop: 24 }} />}

        {data && (
          <>
            <View style={[s.card, { borderColor: COL.cyan }]} testID="proj-ros">
              <Text style={[s.cardTitle, { color: COL.cyan }]}>Rest of Season</Text>
              <Stat l="Projected FPTS" v={data.ros?.projected_fpts?.toFixed(1) || '—'} c={COL.cyan} />
              <Stat l="Blended FPG" v={data.ros?.blended_fpg?.toFixed(2) || '—'} />
              <Stat l="Games Remaining" v={data.ros?.games_remaining || '—'} />
              <View style={s.subStats}>
                <Text style={s.subStat}>Season FPG: <Text style={s.subStatVal}>{data.ros?.season_fpg?.toFixed(2) || '—'}</Text></Text>
                <Text style={s.subStat}>Recent FPG: <Text style={s.subStatVal}>{data.ros?.recent_fpg?.toFixed(2) || '—'}</Text></Text>
              </View>
            </View>

            <View style={[s.card, { borderColor: COL.gold }]} testID="proj-weekly">
              <Text style={[s.cardTitle, { color: COL.gold }]}>Next Week</Text>
              <Stat l="Projected FPTS" v={data.weekly?.projected_fpts?.toFixed(1) || '—'} c={COL.gold} />
              <Stat l="Games" v={data.weekly?.games || '—'} />
              <Stat l="Blended FPG" v={data.weekly?.blended_fpg?.toFixed(2) || '—'} />
            </View>
          </>
        )}
      </ScrollView>

      <Modal animationType="slide" transparent visible={paywall} onRequestClose={() => setPaywall(false)}>
        <View style={s.modalScrim}>
          <View style={s.paywallSheet} testID="proj-paywall-sheet">
            <Text style={{ fontSize: 40, textAlign: 'center' }}>👑</Text>
            <Text style={s.paywallTitle}>Player Projections (Pro)</Text>
            <Text style={[s.cardTitle, { color: COL.gold, textAlign: 'center' }]}>$2.50 / month</Text>
            <Text style={s.sub}>Includes the Trade Analyzer, projections, smart drop suggestions, and the Stat Comparator.</Text>
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 6 }}>
              <TouchableOpacity style={[s.btn, s.btnGhost]} onPress={() => setPaywall(false)} testID="proj-paywall-close">
                <Text style={{ color: COL.text, fontWeight: '600' }}>Maybe later</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[s.btn, s.btnGold]}
                onPress={() => Alert.alert('Stripe coming soon', 'Admin can toggle Pro for testing.')}
                testID="proj-paywall-upgrade"
              >
                <Text style={{ color: '#000', fontWeight: '800' }}>Upgrade</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function Stat({ l, v, c }) {
  return (
    <View style={s.statRow}>
      <Text style={s.statLabel}>{l}</Text>
      <Text style={[s.statValue, c && { color: c }]}>{v}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COL.bg },
  scroll: { padding: 12, gap: 12, paddingBottom: 32 },
  title: { color: COL.text, fontSize: 22, fontWeight: '800' },
  sub: { color: COL.sub, fontSize: 12 },

  searchBlock: { gap: 4 },
  input: { backgroundColor: COL.card, borderWidth: 1, borderColor: COL.border, color: COL.text, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14 },
  resultRow: { backgroundColor: COL.card, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  resultName: { color: COL.text, fontSize: 14 },
  resultMeta: { color: COL.muted, fontSize: 11 },

  card: { backgroundColor: COL.card, borderWidth: 1, borderColor: COL.border, borderRadius: 12, padding: 14, gap: 8 },
  cardTitle: { fontSize: 12, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 },
  playerName: { color: COL.text, fontSize: 18, fontWeight: '700' },
  playerMeta: { color: COL.muted, fontSize: 12 },

  statRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 4 },
  statLabel: { color: COL.sub, fontSize: 13 },
  statValue: { color: COL.text, fontSize: 16, fontWeight: '700' },
  subStats: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6, paddingTop: 6, borderTopWidth: 1, borderTopColor: COL.border },
  subStat: { color: COL.muted, fontSize: 11 },
  subStatVal: { color: COL.text, fontWeight: '700' },

  btn: { paddingVertical: 12, alignItems: 'center', justifyContent: 'center', borderRadius: 10 },
  btnGhost: { backgroundColor: 'transparent', borderWidth: 1, borderColor: COL.border, flex: 1 },
  btnGold: { backgroundColor: COL.gold, flex: 1 },

  modalScrim: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  paywallSheet: { backgroundColor: COL.card, borderTopLeftRadius: 16, borderTopRightRadius: 16, padding: 20, gap: 10 },
  paywallTitle: { color: COL.text, fontSize: 20, fontWeight: '800', textAlign: 'center' },
});
