import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { capSummary, formatMillions } from '../lib/cap';

// Team salary-cap card (mirrors the web TeamSalaryCap widget). Renders nothing
// when the league has no cap.
export default function TeamCapCard({ compliance }) {
  const c = capSummary(compliance);
  if (!c) return null;
  const tiles = [
    { key: 'limit', label: 'Cap Limit', value: formatMillions(c.limit) },
    { key: 'used', label: 'Cap Used', value: formatMillions(c.used) },
    { key: 'remaining', label: c.over ? 'Over Cap By' : 'Cap Remaining', value: `${c.over ? '−' : ''}${formatMillions(Math.abs(c.remaining))}`, tone: c.over ? 'bad' : 'good' },
    { key: 'slots', label: 'Retention Slots', value: `${c.slotsRemaining} / ${c.slotsTotal}` },
    { key: 'retained', label: 'Retained Salary', value: formatMillions(c.retained) },
  ];
  return (
    <View style={s.card} testID="team-salary-cap-card">
      <View style={s.head}>
        <Text style={s.title}>SALARY CAP</Text>
        {c.over ? <Text style={s.overBadge} testID="cap-over-badge">⚠ OVER CAP</Text> : null}
      </View>
      <View style={s.metaRow}>
        <Text style={s.meta}>Used: {formatMillions(c.used)}</Text>
        <Text style={s.meta}>Limit: {formatMillions(c.limit)}</Text>
      </View>
      <View style={s.barBg}><View style={[s.barFill, c.over && s.barOver, { width: `${c.pct}%` }]} /></View>
      {c.over && c.overDetail ? <Text style={s.overDetail}>{c.overDetail}</Text> : null}
      <View style={s.tiles}>
        {tiles.map((t) => (
          <View key={t.key} style={s.tile} testID={`cap-tile-${t.key}`}>
            <Text style={s.tileLabel}>{t.label}</Text>
            <Text style={[s.tileValue, t.tone === 'bad' && s.bad, t.tone === 'good' && s.good]}>{t.value}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  card: { margin: 10, padding: 14, backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  title: { color: '#fff', fontSize: 13, fontWeight: '800', letterSpacing: 1 },
  overBadge: { color: '#FF3B30', fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  meta: { color: '#A1A1AA', fontSize: 11 },
  barBg: { height: 8, backgroundColor: '#1A1A1A', borderRadius: 4, overflow: 'hidden' },
  barFill: { height: '100%', backgroundColor: '#00D2FF', borderRadius: 4 },
  barOver: { backgroundColor: '#FF3B30' },
  overDetail: { color: '#FF3B30', fontSize: 11, marginTop: 6, fontWeight: '600' },
  tiles: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  tile: { flexGrow: 1, flexBasis: '30%', backgroundColor: 'rgba(255,255,255,0.04)', borderRadius: 8, padding: 8, alignItems: 'center' },
  tileLabel: { color: '#A1A1AA', fontSize: 10, marginBottom: 2 },
  tileValue: { color: '#fff', fontSize: 13, fontWeight: '700' },
  good: { color: '#34C759' },
  bad: { color: '#FF3B30' },
});
