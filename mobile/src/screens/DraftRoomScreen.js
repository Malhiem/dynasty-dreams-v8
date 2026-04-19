import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, TextInput, TouchableOpacity, StyleSheet, SafeAreaView } from 'react-native';
import api from '../lib/api';
import { useDraftSocket } from '../hooks/useSocket';
import { useAuth } from '../contexts/AuthContext';

export default function DraftRoomScreen({ route }) {
  const draftId = route?.params?.draftId;
  const { user } = useAuth();
  const [draft, setDraft] = useState(null);
  const [players, setPlayers] = useState([]);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [search, setSearch] = useState('');

  const fetchDraft = async () => {
    if (!draftId) return;
    try {
      const { data } = await api.get(`/drafts/${draftId}`);
      setDraft(data);
      setChatMessages(data.chat_messages || []);
    } catch (e) { console.error(e); }
  };

  const fetchPlayers = async () => {
    if (!draftId) return;
    try {
      const params = new URLSearchParams({ limit: '30' });
      if (search) params.append('search', search);
      const { data } = await api.get(`/drafts/${draftId}/eligible-players?${params}`);
      setPlayers(data.players || []);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { fetchDraft(); fetchPlayers(); }, [draftId]);
  useEffect(() => { const t = setTimeout(fetchPlayers, 300); return () => clearTimeout(t); }, [search]);

  const { connected } = useDraftSocket(draftId, {
    userId: user?.id,
    onDraftPick: () => { fetchDraft(); fetchPlayers(); },
    onChatMessage: (msg) => setChatMessages(prev => [...prev, msg]),
    onDraftCompleted: fetchDraft,
  });

  const handlePick = async (playerId) => {
    try { await api.post(`/drafts/${draftId}/pick`, { player_id: playerId }); fetchDraft(); fetchPlayers(); } catch (e) { console.error(e); }
  };

  const handleChat = async () => {
    if (!chatInput.trim()) return;
    try { await api.post(`/drafts/${draftId}/chat`, { text: chatInput.trim() }); setChatInput(''); fetchDraft(); } catch (e) { console.error(e); }
  };

  const picks = draft?.picks || [];
  const isActive = draft?.status === 'active';

  return (
    <SafeAreaView style={s.container}>
      <ScrollView>
        <View style={s.header}>
          <Text style={s.title}>DRAFT ROOM</Text>
          <View style={s.statusRow}>
            <View style={[s.statusDot, { backgroundColor: connected ? '#34C759' : '#FF3B30' }]} />
            <Text style={s.statusText}>{draft?.status || 'loading'} · {picks.length} picks</Text>
          </View>
        </View>

        {/* Recent Picks */}
        {picks.length > 0 && <View style={s.section}>
          <Text style={s.sectionTitle}>RECENT PICKS</Text>
          {picks.slice(-5).reverse().map((p, i) => (
            <View key={i} style={s.pickRow}>
              <Text style={s.pickNum}>#{p.overall}</Text>
              <Text style={s.pickPlayer}>{p.player?.name}</Text>
              <Text style={s.pickTeam}>{p.team}</Text>
            </View>
          ))}
        </View>}

        {/* Player Search */}
        <View style={s.section}>
          <Text style={s.sectionTitle}>AVAILABLE PLAYERS</Text>
          <TextInput style={s.searchInput} placeholder="Search..." placeholderTextColor="#52525B" value={search} onChangeText={setSearch} />
          {players.slice(0, 15).map(p => (
            <TouchableOpacity key={p.id} style={s.playerRow} onPress={() => isActive && handlePick(p.id)}>
              <View style={s.posBadge}><Text style={s.posText}>{p.position}</Text></View>
              <View style={s.info}><Text style={s.playerName}>{p.name}</Text><Text style={s.playerMeta}>{p.nhlTeam} · {p.pts}P</Text></View>
              {isActive && <View style={s.pickBtn}><Text style={s.pickBtnText}>Pick</Text></View>}
            </TouchableOpacity>
          ))}
        </View>

        {/* Chat */}
        <View style={s.section}>
          <Text style={s.sectionTitle}>DRAFT CHAT</Text>
          {chatMessages.slice(-10).map(m => (
            <View key={m.id} style={[s.chatMsg, m.type === 'pick' && s.chatPick]}>
              <Text style={s.chatSender}>{m.sender}</Text>
              <Text style={s.chatText}>{m.text}</Text>
            </View>
          ))}
          <View style={s.chatBar}>
            <TextInput style={s.chatInput} placeholder="Message..." placeholderTextColor="#52525B" value={chatInput} onChangeText={setChatInput} onSubmitEditing={handleChat} />
            <TouchableOpacity style={s.sendBtn} onPress={handleChat}><Text style={s.sendText}>Send</Text></TouchableOpacity>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  header: { padding: 20 },
  title: { fontSize: 22, fontWeight: '800', color: '#fff' },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { color: '#A1A1AA', fontSize: 12 },
  section: { padding: 16 },
  sectionTitle: { fontSize: 12, fontWeight: '700', color: '#A1A1AA', letterSpacing: 1, marginBottom: 10 },
  pickRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 6, gap: 8 },
  pickNum: { color: '#A1A1AA', fontSize: 12, width: 30 },
  pickPlayer: { color: '#fff', fontSize: 13, fontWeight: '600', flex: 1 },
  pickTeam: { color: '#A1A1AA', fontSize: 11 },
  searchInput: { backgroundColor: '#141414', borderRadius: 8, padding: 10, color: '#fff', marginBottom: 10 },
  playerRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)' },
  posBadge: { width: 32, height: 32, borderRadius: 6, backgroundColor: '#00D2FF20', alignItems: 'center', justifyContent: 'center' },
  posText: { color: '#00D2FF', fontSize: 11, fontWeight: '700' },
  info: { flex: 1, marginLeft: 10 },
  playerName: { color: '#fff', fontSize: 13, fontWeight: '600' },
  playerMeta: { color: '#A1A1AA', fontSize: 10 },
  pickBtn: { backgroundColor: '#00D2FF', paddingHorizontal: 12, paddingVertical: 5, borderRadius: 6 },
  pickBtnText: { color: '#000', fontSize: 11, fontWeight: '700' },
  chatMsg: { padding: 8, backgroundColor: '#141414', borderRadius: 6, marginBottom: 4 },
  chatPick: { backgroundColor: '#00D2FF10', borderWidth: 1, borderColor: '#00D2FF30' },
  chatSender: { color: '#00D2FF', fontSize: 11, fontWeight: '700' },
  chatText: { color: '#A1A1AA', fontSize: 12 },
  chatBar: { flexDirection: 'row', gap: 8, marginTop: 8 },
  chatInput: { flex: 1, backgroundColor: '#141414', borderRadius: 8, padding: 10, color: '#fff' },
  sendBtn: { backgroundColor: '#00D2FF', borderRadius: 8, paddingHorizontal: 14, justifyContent: 'center' },
  sendText: { color: '#000', fontWeight: '700' },
});
