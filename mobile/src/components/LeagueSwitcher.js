import React from 'react';
import { ScrollView, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useLeague } from '../contexts/LeagueContext';

// Chip row to pick the active league. Hidden when the user is in 0-1 leagues.
export default function LeagueSwitcher() {
  const { leagues, leagueId, select } = useLeague();
  if (leagues.length < 2) return null;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.bar} contentContainerStyle={s.inner} testID="league-switcher">
      {leagues.map((l) => {
        const active = l.id === leagueId;
        return (
          <TouchableOpacity key={l.id} testID={`league-chip-${l.id}`} onPress={() => select(l.id)} style={[s.chip, active && s.chipActive]}>
            <Text style={[s.text, active && s.textActive]} numberOfLines={1}>{l.name}</Text>
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  bar: { flexGrow: 0, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.08)' },
  inner: { paddingHorizontal: 10, paddingVertical: 8, gap: 8 },
  chip: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 16, borderWidth: 1, borderColor: 'rgba(255,255,255,0.15)', maxWidth: 200 },
  chipActive: { borderColor: '#00D2FF', backgroundColor: '#00D2FF20' },
  text: { color: '#A1A1AA', fontSize: 12, fontWeight: '600' },
  textActive: { color: '#00D2FF' },
});
