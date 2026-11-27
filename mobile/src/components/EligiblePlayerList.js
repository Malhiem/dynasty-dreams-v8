import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native';
import LoadError from './LoadError';
import { remainingCount } from '../lib/eligible';

// Rows + count + "Load more" for the eligible-player list. `renderRow` draws a
// row so the draft and auction screens keep their own look and actions.
export default function EligiblePlayerList({ list, renderRow, emptyText = 'No players match' }) {
  const { players, total, hasMore, loading, loadingMore, error, loadMore, reload } = list;
  return (
    <View testID="eligible-list">
      <LoadError message={error} onRetry={reload} testID="eligible-error" />
      {!error ? <Text style={s.count} testID="eligible-count">{loading ? 'Loading…' : `${total} available`}</Text> : null}
      {players.map(renderRow)}
      {!loading && !error && players.length === 0 ? <Text style={s.empty}>{emptyText}</Text> : null}
      {hasMore ? (
        <TouchableOpacity style={s.more} onPress={loadMore} disabled={loadingMore} testID="eligible-load-more">
          {loadingMore ? <ActivityIndicator color="#00D2FF" /> : <Text style={s.moreText}>Load more ({remainingCount(total, players.length)} remaining)</Text>}
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  count: { color: '#A1A1AA', fontSize: 11, marginBottom: 6 },
  empty: { color: '#A1A1AA', textAlign: 'center', paddingVertical: 14 },
  more: { marginTop: 8, paddingVertical: 10, alignItems: 'center', borderRadius: 8, borderWidth: 1, borderColor: '#00D2FF' },
  moreText: { color: '#00D2FF', fontWeight: '700' },
});
