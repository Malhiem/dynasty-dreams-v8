import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { RETENTION_OPTIONS, retentionOption } from '../lib/cap';

// A / B / C salary-retention preference (own team, cap leagues only).
export default function RetentionPicker({ value, onChange, disabled }) {
  const current = retentionOption(value);
  return (
    <View style={s.wrap} testID="team-retention-toggle">
      <Text style={s.label}>SALARY RETENTION</Text>
      <View style={s.row}>
        {RETENTION_OPTIONS.map((o) => {
          const active = o.value === current.value;
          return (
            <TouchableOpacity
              key={o.value}
              disabled={disabled}
              testID={`team-retention-${o.value}`}
              accessibilityLabel={o.label}
              onPress={() => !active && onChange(o.value)}
              style={[s.btn, active && { borderColor: o.color, backgroundColor: 'rgba(255,255,255,0.06)' }, disabled && s.dim]}
            >
              <Text style={[s.btnText, { color: active ? o.color : '#A1A1AA' }]}>{o.short}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
      <Text style={[s.hint, { color: current.color }]}>{current.label}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { marginHorizontal: 10, marginBottom: 10, padding: 12, backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
  label: { color: '#A1A1AA', fontSize: 10, letterSpacing: 1, marginBottom: 8 },
  row: { flexDirection: 'row', gap: 8 },
  btn: { flex: 1, paddingVertical: 8, alignItems: 'center', borderRadius: 8, borderWidth: 1, borderColor: 'rgba(255,255,255,0.12)' },
  btnText: { fontWeight: '800', fontSize: 14 },
  dim: { opacity: 0.5 },
  hint: { marginTop: 8, fontSize: 11 },
});
