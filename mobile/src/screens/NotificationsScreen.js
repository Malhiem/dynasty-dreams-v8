import React, { useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, SafeAreaView, RefreshControl } from 'react-native';
import api from '../lib/api';

export default function NotificationsScreen() {
  const [notifs, setNotifs] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchNotifs = async () => {
    try { const { data } = await api.get('/notifications?limit=30'); setNotifs(data); } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { fetchNotifs(); }, []);

  const handleMarkRead = async (id) => {
    try {
      await api.post(`/notifications/${id}/read`);
      setNotifs(prev => prev.map(n => n._id === id ? { ...n, read: true } : n));
    } catch (e) { console.error(e); }
  };

  const handleMarkAll = async () => {
    try {
      await api.post('/notifications/read-all');
      setNotifs(prev => prev.map(n => ({ ...n, read: true })));
    } catch (e) { console.error(e); }
  };

  const unread = notifs.filter(n => !n.read).length;

  return (
    <SafeAreaView style={s.container}>
      {unread > 0 && (
        <TouchableOpacity style={s.markAllBar} onPress={handleMarkAll}>
          <Text style={s.markAllText}>Mark all {unread} as read</Text>
        </TouchableOpacity>
      )}
      <FlatList
        data={notifs}
        keyExtractor={item => item._id}
        renderItem={({ item }) => (
          <TouchableOpacity style={[s.notifRow, !item.read && s.unread]} onPress={() => handleMarkRead(item._id)}>
            <View style={s.content}>
              <View style={s.titleRow}>
                <Text style={[s.title, !item.read && s.titleBold]}>{item.title}</Text>
                {!item.read && <View style={s.dot} />}
              </View>
              <Text style={s.message}>{item.message}</Text>
              <Text style={s.time}>{new Date(item.created_at).toLocaleString()}</Text>
            </View>
          </TouchableOpacity>
        )}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={fetchNotifs} tintColor="#00D2FF" />}
        contentContainerStyle={s.list}
        ListEmptyComponent={<View style={s.empty}><Text style={s.emptyText}>No notifications</Text></View>}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  markAllBar: { padding: 12, backgroundColor: '#00D2FF20', borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.1)' },
  markAllText: { color: '#00D2FF', textAlign: 'center', fontSize: 13, fontWeight: '600' },
  list: { padding: 8 },
  notifRow: { padding: 14, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)' },
  unread: { backgroundColor: '#00D2FF08' },
  content: {},
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 14, color: '#A1A1AA' },
  titleBold: { color: '#fff', fontWeight: '600' },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#00D2FF' },
  message: { fontSize: 13, color: '#A1A1AA', marginTop: 4 },
  time: { fontSize: 10, color: '#52525B', marginTop: 6 },
  empty: { alignItems: 'center', paddingTop: 60 },
  emptyText: { color: '#A1A1AA' },
});
