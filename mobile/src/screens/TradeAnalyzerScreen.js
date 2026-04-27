/**
 * TradeAnalyzerScreen — Pro-paywalled trade evaluator (mobile parity with
 * /trade-analyzer on web). Lets the user build two sides (players + picks +
 * FAAB), POSTs to /trade-analyzer/analyze, and renders winner + verdict +
 * fairness + per-asset breakdown. Free tier: 1 analysis / year. 402 →
 * paywall sheet.
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
  cyan: '#00D2FF', gold: '#FFB020', emerald: '#10B981',
  amber: '#F59E0B', orange: '#FB923C', rose: '#FB7185',
};

const verdictTone = (v) => {
  if (v === 'Fair Trade') return COL.emerald;
  if (v === 'Slightly Lopsided') return COL.amber;
  if (v === 'Lopsided') return COL.orange;
  return COL.rose;
};

function PlayerSearchAdd({ sideKey, onAdd }) {
  const [q, setQ] = useState('');
  const [opts, setOpts] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!q || q.length < 2) { setOpts([]); return; }
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const { data } = await api.get(`/players?search=${encodeURIComponent(q)}&limit=8`);
        setOpts(data?.players || []);
      } catch { setOpts([]); }
      setLoading(false);
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <View>
      <TextInput
        testID={`analyzer-add-player-${sideKey}`}
        value={q}
        onChangeText={setQ}
        placeholder="Add player…"
        placeholderTextColor={COL.muted}
        style={s.input}
      />
      {loading && <ActivityIndicator size="small" color={COL.cyan} style={{ marginTop: 6 }} />}
      {opts.length > 0 && (
        <View style={s.dropdown}>
          {opts.map((p) => (
            <TouchableOpacity
              key={p._id}
              testID={`analyzer-search-result-${sideKey}-${p._id}`}
              onPress={() => { onAdd(p); setQ(''); setOpts([]); }}
              style={s.dropdownRow}
            >
              <Text style={s.dropdownName}>{p.name}</Text>
              <Text style={s.dropdownMeta}>{p.position} · {p.team}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

function PickAddBlock({ sideKey, onAdd }) {
  const [round, setRound] = useState(1);
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear + 1);
  return (
    <View style={s.pickRow}>
      <View style={s.pickPickers}>
        <TouchableOpacity
          testID={`analyzer-pick-year-${sideKey}`}
          onPress={() => setYear(y => (y >= currentYear + 4 ? currentYear : y + 1))}
          style={s.pickerBtn}
        >
          <Text style={s.pickerLabel}>Year</Text>
          <Text style={s.pickerVal}>{year}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          testID={`analyzer-pick-round-${sideKey}`}
          onPress={() => setRound(r => (r >= 7 ? 1 : r + 1))}
          style={s.pickerBtn}
        >
          <Text style={s.pickerLabel}>Round</Text>
          <Text style={s.pickerVal}>R{round}</Text>
        </TouchableOpacity>
      </View>
      <TouchableOpacity
        testID={`analyzer-add-pick-${sideKey}`}
        onPress={() => onAdd({ year, round, slot: 6 })}
        style={s.addBtn}
      >
        <Text style={s.addBtnText}>+ Pick</Text>
      </TouchableOpacity>
    </View>
  );
}

function SideBuilder({ sideKey, side, setSide }) {
  const removePlayer = (id) => setSide(prev => ({ ...prev, players: prev.players.filter(p => p._id !== id) }));
  const removePick = (i) => setSide(prev => ({ ...prev, picks: prev.picks.filter((_, idx) => idx !== i) }));
  return (
    <View style={[s.card, { borderColor: sideKey === 'a' ? COL.cyan : COL.gold }]} testID={`analyzer-side-${sideKey}`}>
      <Text style={[s.sideTitle, { color: sideKey === 'a' ? COL.cyan : COL.gold }]}>
        Side {sideKey.toUpperCase()}
      </Text>

      <PlayerSearchAdd sideKey={sideKey} onAdd={(p) =>
        setSide(prev => prev.players.find(x => x._id === p._id) ? prev : ({ ...prev, players: [...prev.players, p] }))
      } />

      {side.players.map(p => (
        <View key={p._id} style={s.assetRow} testID={`analyzer-player-${sideKey}-${p._id}`}>
          <View style={{ flex: 1 }}>
            <Text style={s.assetName}>{p.name}</Text>
            <Text style={s.assetMeta}>{p.position} · {p.team}</Text>
          </View>
          <TouchableOpacity onPress={() => removePlayer(p._id)}><Text style={s.removeX}>×</Text></TouchableOpacity>
        </View>
      ))}

      <PickAddBlock sideKey={sideKey} onAdd={(pk) => setSide(prev => ({ ...prev, picks: [...prev.picks, pk] }))} />
      {side.picks.map((pk, i) => (
        <View key={i} style={s.assetRow}>
          <Text style={[s.assetName, { flex: 1 }]}>{pk.year} · R{pk.round}</Text>
          <TouchableOpacity onPress={() => removePick(i)}><Text style={s.removeX}>×</Text></TouchableOpacity>
        </View>
      ))}

      <View style={s.faabRow}>
        <Text style={s.faabLabel}>FAAB $</Text>
        <TextInput
          testID={`analyzer-faab-${sideKey}`}
          keyboardType="numeric"
          value={String(side.faab || 0)}
          onChangeText={(v) => setSide(prev => ({ ...prev, faab: parseInt(v || '0', 10) || 0 }))}
          style={s.faabInput}
          placeholderTextColor={COL.muted}
        />
      </View>
    </View>
  );
}

function ResultCard({ result }) {
  const winner = result.winner;
  return (
    <View style={[s.card, { borderColor: COL.cyan }]} testID="analyzer-result">
      <View style={s.resultTop}>
        <View style={s.resultBlock}>
          <Text style={s.resultLabel}>Side A receives</Text>
          <Text testID="analyzer-value-a" style={[s.resultValue, { color: COL.cyan }]}>{result.side_b.total_value.toFixed(1)}</Text>
        </View>
        <View style={s.resultBlock}>
          <View testID="analyzer-verdict" style={[s.verdictPill, { borderColor: verdictTone(result.verdict), backgroundColor: `${verdictTone(result.verdict)}22` }]}>
            <Text style={{ color: verdictTone(result.verdict), fontWeight: '700' }}>{result.verdict}</Text>
          </View>
          <Text style={s.fairnessText}>Fairness <Text style={{ color: COL.text, fontWeight: '700' }}>{result.fairness_pct}%</Text></Text>
          <Text style={s.deltaText}>
            {winner === 'tie' ? '— Even' : winner === 'a' ? `↑ A wins by ${Math.abs(result.delta).toFixed(1)}` : `↓ B wins by ${Math.abs(result.delta).toFixed(1)}`}
          </Text>
        </View>
        <View style={s.resultBlock}>
          <Text style={s.resultLabel}>Side B receives</Text>
          <Text testID="analyzer-value-b" style={[s.resultValue, { color: COL.gold }]}>{result.side_a.total_value.toFixed(1)}</Text>
        </View>
      </View>

      {[{ key: 'a', side: result.side_a, c: COL.cyan }, { key: 'b', side: result.side_b, c: COL.gold }].map(({ key, side, c }) => (
        <View key={key} style={s.breakdownBlock} testID={`analyzer-breakdown-${key}`}>
          <Text style={[s.breakdownTitle, { color: c }]}>Side {key.toUpperCase()} outgoing breakdown</Text>
          {side.players.map(p => (
            <View key={p.player_id} style={s.breakdownRow}>
              <View style={{ flex: 1 }}>
                <Text style={s.assetName}>{p.name}</Text>
                <Text style={s.assetMeta}>{p.position} · {p.team} · {p.blended_fpg.toFixed(2)} FPG</Text>
              </View>
              <Text style={[s.assetName, { color: c }]}>{p.value.toFixed(1)}</Text>
            </View>
          ))}
          {side.picks.map((pk, i) => (
            <View key={i} style={s.breakdownRow}>
              <Text style={[s.assetName, { flex: 1 }]}>{pk.label}</Text>
              <Text style={[s.assetName, { color: c }]}>{pk.value.toFixed(1)}</Text>
            </View>
          ))}
          {side.faab > 0 && (
            <View style={s.breakdownRow}>
              <Text style={[s.assetName, { flex: 1 }]}>${side.faab} FAAB</Text>
              <Text style={[s.assetName, { color: c }]}>{side.faab_value.toFixed(1)}</Text>
            </View>
          )}
          <View style={[s.breakdownRow, { borderTopWidth: 1, borderTopColor: COL.border, paddingTop: 6 }]}>
            <Text style={[s.assetName, { flex: 1, color: COL.sub }]}>Total</Text>
            <Text style={[s.resultValue, { color: c, fontSize: 18 }]}>{side.total_value.toFixed(1)}</Text>
          </View>
        </View>
      ))}
    </View>
  );
}

function PaywallSheet({ visible, onClose }) {
  return (
    <Modal animationType="slide" transparent visible={visible} onRequestClose={onClose}>
      <View style={s.modalScrim}>
        <View style={s.paywallSheet} testID="analyzer-paywall-sheet">
          <Text style={s.paywallEmoji}>👑</Text>
          <Text style={s.paywallTitle}>Trade Analyzer Pro</Text>
          <Text style={s.paywallPrice}>$2.50 / month</Text>
          <View style={s.paywallList}>
            <Text style={s.paywallBullet}>✦ Unlimited trade analyses</Text>
            <Text style={s.paywallBullet}>✦ Player projections (ROS + weekly)</Text>
            <Text style={s.paywallBullet}>✦ Smart drop suggestions</Text>
            <Text style={s.paywallBullet}>✦ Stat Comparator (unlimited)</Text>
          </View>
          <Text style={s.paywallNote}>You've used your 1 free trade analysis this year.</Text>
          <View style={s.paywallActions}>
            <TouchableOpacity onPress={onClose} style={[s.btn, s.btnGhost]} testID="analyzer-paywall-close">
              <Text style={s.btnGhostText}>Maybe later</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => Alert.alert('Stripe coming soon', 'Admin can toggle Pro for testing.')}
              style={[s.btn, s.btnGold]}
              testID="analyzer-paywall-upgrade"
            >
              <Text style={s.btnGoldText}>Upgrade</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

export default function TradeAnalyzerScreen({ route }) {
  const leagueId = route?.params?.leagueId || null;
  const [sideA, setSideA] = useState({ players: [], picks: [], faab: 0 });
  const [sideB, setSideB] = useState({ players: [], picks: [], faab: 0 });
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [paywallOpen, setPaywallOpen] = useState(false);
  const [status, setStatus] = useState(null);

  const refreshStatus = useCallback(() => {
    api.get('/users/me/analyzer-status').then(r => setStatus(r.data)).catch(() => {});
  }, []);
  useEffect(() => { refreshStatus(); }, [refreshStatus]);

  const isEmpty = (s) => !s.players.length && !s.picks.length && !s.faab;
  const buildSidePayload = (sd) => ({ players: sd.players.map(p => p._id), picks: sd.picks, faab: sd.faab });

  const runAnalyze = async () => {
    if (isEmpty(sideA) || isEmpty(sideB)) {
      Alert.alert('Add at least one asset to each side');
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post('/trade-analyzer/analyze', {
        league_id: leagueId,
        side_a: buildSidePayload(sideA),
        side_b: buildSidePayload(sideB),
      });
      setResult(data);
      refreshStatus();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 402 && detail?.code === 'upgrade_required') {
        setPaywallOpen(true);
      } else {
        Alert.alert('Analyze failed', typeof detail === 'string' ? detail : 'Unknown error');
      }
    } finally { setSubmitting(false); }
  };

  return (
    <SafeAreaView style={s.container} testID="trade-analyzer-screen">
      <ScrollView contentContainerStyle={s.scroll}>
        <View style={s.header}>
          <Text style={s.title}>⚖ Trade Value Analyzer</Text>
          <Text style={s.sub}>Drag in players, picks, and FAAB. We score both sides against your league's rules and call the verdict.</Text>
          {status && (
            <View testID="analyzer-status-strip" style={s.statusStrip}>
              {status.is_pro ? (
                <Text style={[s.statusText, { color: COL.gold }]}>👑 Pro · Unlimited</Text>
              ) : (
                <Text style={s.statusText}>
                  Free · <Text style={{ color: COL.cyan, fontWeight: '700' }}>{status.analyses_remaining}</Text> / {status.free_analyses_per_year} this year
                </Text>
              )}
            </View>
          )}
        </View>

        <SideBuilder sideKey="a" side={sideA} setSide={setSideA} />
        <SideBuilder sideKey="b" side={sideB} setSide={setSideB} />

        <TouchableOpacity
          testID="analyzer-run-btn"
          onPress={runAnalyze}
          disabled={submitting}
          style={[s.btn, s.btnCyan, submitting && { opacity: 0.5 }]}
        >
          <Text style={s.btnCyanText}>{submitting ? 'Analyzing…' : 'Analyze Trade →'}</Text>
        </TouchableOpacity>

        {result && <ResultCard result={result} />}
      </ScrollView>
      <PaywallSheet visible={paywallOpen} onClose={() => setPaywallOpen(false)} />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COL.bg },
  scroll: { padding: 12, gap: 12, paddingBottom: 32 },
  header: { gap: 6 },
  title: { color: COL.text, fontSize: 22, fontWeight: '800' },
  sub: { color: COL.sub, fontSize: 12 },
  statusStrip: { marginTop: 4, paddingVertical: 6, paddingHorizontal: 10, backgroundColor: COL.card, borderWidth: 1, borderColor: COL.border, borderRadius: 8, alignSelf: 'flex-start' },
  statusText: { color: COL.sub, fontSize: 12 },

  card: { backgroundColor: COL.card, borderWidth: 1, borderColor: COL.border, borderRadius: 12, padding: 12, gap: 8 },
  sideTitle: { fontWeight: '800', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase' },

  input: { backgroundColor: COL.bg, borderWidth: 1, borderColor: COL.border, color: COL.text, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 10, fontSize: 14 },

  dropdown: { backgroundColor: COL.bg, borderWidth: 1, borderColor: COL.border, borderRadius: 8, marginTop: 4, maxHeight: 220, overflow: 'hidden' },
  dropdownRow: { paddingHorizontal: 10, paddingVertical: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: COL.border },
  dropdownName: { color: COL.text, fontSize: 14 },
  dropdownMeta: { color: COL.muted, fontSize: 11 },

  pickRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  pickPickers: { flexDirection: 'row', gap: 8, flex: 1 },
  pickerBtn: { backgroundColor: COL.bg, borderWidth: 1, borderColor: COL.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, alignItems: 'center', flex: 1 },
  pickerLabel: { color: COL.muted, fontSize: 9, textTransform: 'uppercase' },
  pickerVal: { color: COL.text, fontSize: 14, fontWeight: '700' },

  addBtn: { backgroundColor: '#1A1A1A', borderWidth: 1, borderColor: COL.border, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 8 },
  addBtnText: { color: COL.cyan, fontSize: 12, fontWeight: '700' },

  assetRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: COL.bg, paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, gap: 8 },
  assetName: { color: COL.text, fontSize: 13, fontWeight: '600' },
  assetMeta: { color: COL.muted, fontSize: 10 },
  removeX: { color: COL.rose, fontSize: 18, paddingHorizontal: 6 },

  faabRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 },
  faabLabel: { color: COL.sub, fontSize: 12, width: 60 },
  faabInput: { flex: 1, backgroundColor: COL.bg, borderWidth: 1, borderColor: COL.border, color: COL.text, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, fontSize: 14 },

  btn: { borderRadius: 10, paddingVertical: 12, alignItems: 'center', justifyContent: 'center' },
  btnCyan: { backgroundColor: COL.cyan },
  btnCyanText: { color: '#000', fontWeight: '800', fontSize: 14 },
  btnGhost: { backgroundColor: 'transparent', borderWidth: 1, borderColor: COL.border, flex: 1 },
  btnGhostText: { color: COL.text, fontWeight: '600' },
  btnGold: { backgroundColor: COL.gold, flex: 1 },
  btnGoldText: { color: '#000', fontWeight: '800' },

  resultTop: { flexDirection: 'row', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: COL.border, paddingBottom: 12, marginBottom: 8, gap: 8 },
  resultBlock: { flex: 1, alignItems: 'center', gap: 4 },
  resultLabel: { color: COL.muted, fontSize: 9, letterSpacing: 1, textTransform: 'uppercase', textAlign: 'center' },
  resultValue: { fontSize: 24, fontWeight: '800' },
  verdictPill: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1 },
  fairnessText: { color: COL.sub, fontSize: 11 },
  deltaText: { color: COL.muted, fontSize: 11 },

  breakdownBlock: { marginTop: 8, gap: 4 },
  breakdownTitle: { fontSize: 10, letterSpacing: 1, textTransform: 'uppercase', fontWeight: '700' },
  breakdownRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 6, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: COL.border },

  modalScrim: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  paywallSheet: { backgroundColor: COL.card, borderTopLeftRadius: 16, borderTopRightRadius: 16, padding: 20, gap: 12 },
  paywallEmoji: { fontSize: 40, textAlign: 'center' },
  paywallTitle: { color: COL.text, fontSize: 22, fontWeight: '800', textAlign: 'center' },
  paywallPrice: { color: COL.gold, fontSize: 16, fontWeight: '700', textAlign: 'center' },
  paywallList: { backgroundColor: COL.bg, borderRadius: 10, padding: 12, gap: 6 },
  paywallBullet: { color: COL.sub, fontSize: 13 },
  paywallNote: { color: COL.muted, fontSize: 11, textAlign: 'center' },
  paywallActions: { flexDirection: 'row', gap: 10 },
});
