import React, { useState, useEffect } from 'react';
import { View, Text, FlatList, TextInput, TouchableOpacity, StyleSheet, SafeAreaView, RefreshControl } from 'react-native';
import api from '../lib/api';
import { useAuth } from '../contexts/AuthContext';

export default function ActivityFeedScreen() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [leagueId, setLeagueId] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchFeed = async (lid) => {
    try {
      const { data } = await api.get(`/activity/${lid}?limit=30`);
      setItems(data.items || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => {
    const init = async () => {
      try {
        const { data } = await api.get('/leagues?my_leagues=true');
        if (data.length > 0) { setLeagueId(data[0].id); await fetchFeed(data[0].id); }
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    init();
  }, []);

  const handleSendChat = async () => {
    if (!chatInput.trim() || !leagueId) return;
    try {
      await api.post(`/activity/${leagueId}/chat`, { text: chatInput.trim() });
      setChatInput('');
      await fetchFeed(leagueId);
    } catch (e) { console.error(e); }
  };

  const eventIcons = { chat: '💬', roster_add: '➕', roster_drop: '➖', contract_signed: '📝', trade_proposed: '🔄', week_simulated: '📊' };

  return (
    <SafeAreaView style={s.container}>
      <View style={s.chatBar}>
        <TextInput style={s.chatInput} placeholder="Post to league..." placeholderTextColor="#52525B" value={chatInput} onChangeText={setChatInput} onSubmitEditing={handleSendChat} />
        <TouchableOpacity style={s.sendBtn} onPress={handleSendChat}><Text style={s.sendText}>Send</Text></TouchableOpacity>
      </View>
      <FlatList
        data={items}
        keyExtractor={item => item._id}
        renderItem={({ item }) => (
          <View style={[s.feedItem, item.event_type === 'chat' && s.chatItem]}>
            <Text style={s.icon}>{eventIcons[item.event_type] || '📋'}</Text>
            <View style={s.content}>
              {item.event_type === 'chat' && <Text style={s.sender}>{item.metadata?.sender || 'User'}</Text>}
              <Text style={s.message}>{item.message}</Text>
              <Text style={s.time}>{new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</Text>
            </View>
          </View>
        )}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={() => leagueId && fetchFeed(leagueId)} tintColor="#00D2FF" />}
        contentContainerStyle={s.list}
        ListEmptyComponent={<View style={s.empty}><Text style={s.emptyText}>{loading ? 'Loading...' : 'No activity yet'}</Text></View>}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  chatBar: { flexDirection: 'row', padding: 12, gap: 8, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.1)' },
  chatInput: { flex: 1, backgroundColor: '#141414', borderRadius: 8, paddingHorizontal: 14, paddingVertical: 10, color: '#fff', fontSize: 14 },
  sendBtn: { backgroundColor: '#00D2FF', borderRadius: 8, paddingHorizontal: 16, justifyContent: 'center' },
  sendText: { color: '#000', fontWeight: '700', fontSize: 13 },
  list: { padding: 12 },
  feedItem: { flexDirection: 'row', padding: 12, backgroundColor: '#141414', borderRadius: 8, marginBottom: 8, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
  chatItem: { backgroundColor: 'transparent', borderColor: 'rgba(255,255,255,0.05)' },
  icon: { fontSize: 20, marginRight: 12, marginTop: 2 },
  content: { flex: 1 },
  sender: { color: '#00D2FF', fontSize: 12, fontWeight: '700', marginBottom: 2 },
  message: { color: '#fff', fontSize: 13 },
  time: { color: '#52525B', fontSize: 10, marginTop: 4 },
  empty: { alignItems: 'center', paddingTop: 60 },
  emptyText: { color: '#A1A1AA' },
});
