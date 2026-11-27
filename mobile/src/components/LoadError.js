import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';

// Shown when a screen could not load its data. Distinguishes "failed" from
// "empty" and gives the user a way to try again.
export default function LoadError({ message, onRetry, testID = 'load-error' }) {
  if (!message) return null;
  return (
    <View style={s.wrap} testID={testID}>
      <Text style={s.text}>{message}</Text>
      {onRetry ? (
        <TouchableOpacity style={s.btn} onPress={onRetry} testID={`${testID}-retry`}>
          <Text style={s.btnText}>Retry</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { margin: 16, padding: 16, borderRadius: 10, backgroundColor: '#FF3B3015', borderWidth: 1, borderColor: '#FF3B3040', alignItems: 'center' },
  text: { color: '#fff', fontSize: 14, textAlign: 'center' },
  btn: { marginTop: 12, paddingHorizontal: 22, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: '#00D2FF' },
  btnText: { color: '#00D2FF', fontWeight: '700' },
});
