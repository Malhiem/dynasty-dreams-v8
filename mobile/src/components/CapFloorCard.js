import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { floorSummary, formatMillions } from '../lib/cap';

// Cap floor card (mirrors the web Salary Cap page). Renders nothing when the
// league has no floor. Commissioners also see the teams below / near the floor.
export default function CapFloorCard({ watchlist, userId, showWatchlist }) {
  const f = floorSummary(watchlist, userId);
  if (!f) return null;
  return (
    <View style={s.card} testID="cap-floor-card">
      <Text style={s.title}>CAP FLOOR</Text>
      <Text style={s.desc}>
        Minimum team payroll for {f.year || 'this season'}: <Text style={s.amber}>{formatMillions(f.floor)}</Text>. Teams below the floor on the compliance date may be penalised per the league constitution.
      </Text>
      {f.mine ? (
        <View style={s.mineRow}>
          <Text style={s.meta}>Your payroll: <Text style={s.bold}>{formatMillions(f.mine.payroll)}</Text></Text>
          {f.mine.compliant ? (
            <Text style={[s.badge, s.ok]} testID="cap-floor-compliant">Above floor</Text>
          ) : (
            <Text style={[s.badge, s.bad]} testID="cap-floor-below">Below floor · {formatMillions(f.mine.shortfall)} short</Text>
          )}
        </View>
      ) : null}
      <View style={s.years}>
        {[['This year', f.floor], ['Year +1', f.yr1], ['Year +2', f.yr2]].map(([label, v]) => (
          <View key={label} style={s.year}>
            <Text style={s.yearLabel}>{label}</Text>
            <Text style={[s.amber, s.bold]}>{formatMillions(v)}</Text>
          </View>
        ))}
      </View>
      {showWatchlist && f.atRisk.length > 0 ? (
        <View style={s.watch} testID="cap-floor-watchlist">
          <Text style={s.watchTitle}>WATCHLIST · {f.belowCount} below · {f.watchCount} near</Text>
          {f.atRisk.map((t) => (
            <View key={t.team_id} style={s.watchRow}>
              <Text style={s.watchName} numberOfLines={1}>{t.team_name}</Text>
              <Text style={[s.delta, t.delta_to_floor < 0 ? s.badText : s.warnText]}>
                {t.delta_to_floor >= 0 ? '+' : '−'}{formatMillions(Math.abs(t.delta_to_floor))} · {t.status === 'below' ? 'Below' : 'Near'}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  card: { marginHorizontal: 16, marginBottom: 12, padding: 14, backgroundColor: '#141414', borderRadius: 8, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
  title: { color: '#fff', fontSize: 13, fontWeight: '800', letterSpacing: 1, marginBottom: 6 },
  desc: { color: '#A1A1AA', fontSize: 11, lineHeight: 16 },
  amber: { color: '#FBBF24' },
  bold: { fontWeight: '700', color: '#fff' },
  mineRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 },
  meta: { color: '#A1A1AA', fontSize: 12 },
  badge: { fontSize: 11, fontWeight: '700', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, overflow: 'hidden' },
  ok: { color: '#6EE7B7', backgroundColor: '#10B98120' },
  bad: { color: '#FDA4AF', backgroundColor: '#F43F5E20' },
  years: { flexDirection: 'row', gap: 8, marginTop: 12 },
  year: { flex: 1, alignItems: 'center', padding: 8, borderRadius: 8, backgroundColor: 'rgba(255,255,255,0.04)' },
  yearLabel: { color: '#A1A1AA', fontSize: 10, marginBottom: 2 },
  watch: { marginTop: 14, borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.08)', paddingTop: 10 },
  watchTitle: { color: '#A1A1AA', fontSize: 10, letterSpacing: 1, marginBottom: 6 },
  watchRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  watchName: { color: '#fff', fontSize: 12, flex: 1, marginRight: 8 },
  delta: { fontSize: 11, fontWeight: '600' },
  badText: { color: '#FDA4AF' },
  warnText: { color: '#FBBF24' },
});
