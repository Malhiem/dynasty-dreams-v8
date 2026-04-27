import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, FlatList, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, Modal, Alert, RefreshControl, KeyboardAvoidingView, Platform,
} from 'react-native';
import api from '../lib/api';

const COLORS = {
  bg: '#0a0a0a', card: '#141414', border: 'rgba(255,255,255,0.1)',
  text: '#fff', muted: '#A1A1AA', primary: '#00D2FF', accent: '#FFB800',
  danger: '#FF3B5C',
};

const MUTE_DURATIONS = [
  { value: '30m', label: '30 minutes' },
  { value: '1h', label: '1 hour' },
  { value: '4h', label: '4 hours' },
  { value: '12h', label: '12 hours' },
  { value: '24h', label: '24 hours' },
  { value: 'indefinite', label: 'Until I unmute' },
];

function fmtTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function initialsFor(name) {
  if (!name) return '?';
  return name.split(/\s+/).slice(0, 2).map((s) => s[0]?.toUpperCase()).join('');
}

export default function ChatScreen({ route, navigation }) {
  const initialLeagueId = route?.params?.leagueId;
  const [leagueId, setLeagueId] = useState(initialLeagueId || null);

  // Fall back to the user's first league when no leagueId is passed
  useEffect(() => {
    if (leagueId) return;
    (async () => {
      try {
        const { data } = await api.get('/leagues?my_leagues=true');
        if (Array.isArray(data) && data.length) {
          setLeagueId(data[0].id);
        }
      } catch {
        // ignore
      }
    })();
  }, [leagueId]);
  const [channels, setChannels] = useState([]);
  const [maxChannels, setMaxChannels] = useState(12);
  const [members, setMembers] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [actionsFor, setActionsFor] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [me, setMe] = useState(null);
  const [isCommish, setIsCommish] = useState(false);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState('');
  const listRef = useRef(null);

  const loadEverything = useCallback(async () => {
    if (!leagueId) return;
    setLoading(true);
    try {
      const [meR, leagueR, chansR, membersR] = await Promise.all([
        api.get('/auth/me'),
        api.get(`/leagues/${leagueId}`),
        api.get(`/chat/channels?league_id=${leagueId}`),
        api.get(`/chat/league/${leagueId}/members`),
      ]);
      setMe(meR.data);
      const lg = leagueR.data;
      setIsCommish(
        lg?.commissioner_id === meR.data?.id ||
        (lg?.co_commissioners || []).includes(meR.data?.id),
      );
      const list = chansR.data?.channels || [];
      setChannels(list);
      setMaxChannels(chansR.data?.max_channels || 12);
      setMembers(membersR.data?.members || []);
      if (list.length && !list.find((c) => c._id === selectedId)) {
        setSelectedId(list[0]._id);
      }
    } catch (e) {
      console.warn('chat init', e?.response?.data || e?.message);
    } finally {
      setLoading(false);
    }
  }, [leagueId, selectedId]);

  useEffect(() => { loadEverything(); }, [loadEverything]);

  const loadMessages = useCallback(async () => {
    if (!selectedId) { setMessages([]); return; }
    try {
      const { data } = await api.get(`/chat/channels/${selectedId}/messages?limit=200`);
      setMessages(data?.messages || []);
    } catch (e) {
      console.warn('chat msgs', e?.message);
    }
  }, [selectedId]);

  useEffect(() => { loadMessages(); }, [loadMessages]);

  // Poll active channel every 10s
  useEffect(() => {
    if (!selectedId) return undefined;
    const id = setInterval(loadMessages, 10000);
    return () => clearInterval(id);
  }, [selectedId, loadMessages]);

  useEffect(() => {
    if (messages.length && listRef.current) {
      setTimeout(() => listRef.current?.scrollToEnd?.({ animated: true }), 50);
    }
  }, [messages, selectedId]);

  const handleDraftChange = (txt) => {
    setDraft(txt);
    const m = /(^|\s)@([\w-]*)$/.exec(txt);
    if (m) { setMentionOpen(true); setMentionQuery(m[2].toLowerCase()); }
    else { setMentionOpen(false); setMentionQuery(''); }
  };

  const insertMention = (name) => {
    const next = draft.replace(/(^|\s)@([\w-]*)$/, (_, lead) => `${lead}@${name} `);
    setDraft(next);
    setMentionOpen(false);
    setMentionQuery('');
  };

  const filteredMentions = useMemo(() => {
    if (!mentionOpen) return [];
    return members.filter((m) =>
      !mentionQuery
      || m.team_name.toLowerCase().includes(mentionQuery)
      || m.owner_name.toLowerCase().includes(mentionQuery),
    ).slice(0, 5);
  }, [mentionOpen, mentionQuery, members]);

  const send = async () => {
    const text = draft.trim();
    if (!text || !selectedId) return;
    try {
      await api.post(`/chat/channels/${selectedId}/messages`, { content: text });
      setDraft('');
      setMentionOpen(false);
      await loadMessages();
    } catch (e) {
      Alert.alert('Send failed', e?.response?.data?.detail || e.message);
    }
  };

  const handleMute = async (chanId, duration) => {
    try {
      await api.post(`/chat/channels/${chanId}/mute`, { duration });
      await loadEverything();
    } catch (e) {
      Alert.alert('Mute failed', e?.response?.data?.detail || e.message);
    }
    setActionsFor(null);
  };

  const handleDeleteChannel = (chan) => {
    Alert.alert(
      `Delete #${chan.name}?`,
      'This will remove all messages. Default channels cannot be deleted.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete', style: 'destructive', onPress: async () => {
            try {
              await api.delete(`/chat/channels/${chan._id}`);
              if (selectedId === chan._id) setSelectedId(null);
              setActionsFor(null);
              await loadEverything();
            } catch (e) {
              Alert.alert('Delete failed', e?.response?.data?.detail || e.message);
            }
          },
        },
      ],
    );
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await api.post('/chat/channels', { league_id: leagueId, name: newName.trim() });
      setNewName('');
      setCreateOpen(false);
      await loadEverything();
    } catch (e) {
      Alert.alert('Create failed', e?.response?.data?.detail || e.message);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([loadEverything(), loadMessages()]);
    setRefreshing(false);
  };

  const channelList = channels.filter((c) => c.kind === 'channel');
  const dmList = channels.filter((c) => c.kind === 'dm');
  const selectedChan = channels.find((c) => c._id === selectedId);

  const renderChannelRow = (c) => {
    const isSel = c._id === selectedId;
    return (
      <TouchableOpacity
        key={c._id}
        testID={c.kind === 'dm' ? `chat-dm-${c._id}` : `chat-channel-${c.name}`}
        style={[styles.chanRow, isSel && styles.chanRowActive]}
        onPress={() => setSelectedId(c._id)}
        onLongPress={() => setActionsFor(c)}
      >
        <Text style={[styles.chanIcon, isSel && { color: COLORS.primary }]}>
          {c.kind === 'dm' ? initialsFor(c.name) : '#'}
        </Text>
        <Text
          numberOfLines={1}
          style={[styles.chanName, isSel && { color: COLORS.primary, fontWeight: '600' }]}
        >
          {c.name}
        </Text>
        {c.muted && <Text style={styles.muteIcon}>🔕</Text>}
        {c.unread > 0 && !c.muted && (
          <View style={styles.unreadPill}>
            <Text style={styles.unreadTxt}>{c.unread > 99 ? '99+' : c.unread}</Text>
          </View>
        )}
      </TouchableOpacity>
    );
  };

  if (!leagueId) {
    return (
      <View style={[styles.center, { backgroundColor: COLORS.bg }]}>
        <Text style={{ color: COLORS.muted }}>Open a league first to access chat.</Text>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      {/* Channel list */}
      <View style={styles.sidebar}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>
            CHANNELS <Text style={styles.cap}>({channelList.length}/{maxChannels})</Text>
          </Text>
          {isCommish && (
            <TouchableOpacity
              testID="chat-new-channel-btn"
              disabled={channelList.length >= maxChannels}
              onPress={() => setCreateOpen(true)}
              style={[styles.newBtn, channelList.length >= maxChannels && { opacity: 0.4 }]}
            >
              <Text style={styles.newBtnTxt}>＋</Text>
            </TouchableOpacity>
          )}
        </View>
        <FlatList
          horizontal
          showsHorizontalScrollIndicator={false}
          data={[...channelList, ...dmList]}
          keyExtractor={(c) => c._id}
          renderItem={({ item }) => renderChannelRow(item)}
          contentContainerStyle={{ paddingHorizontal: 8, gap: 6 }}
        />
      </View>

      {/* Active channel header */}
      <View style={styles.activeHeader}>
        <Text style={styles.activeName} testID="chat-active-channel-name">
          {selectedChan ? (selectedChan.kind === 'dm' ? selectedChan.name : `#${selectedChan.name}`) : 'Pick a channel'}
        </Text>
        {selectedChan?.muted && <Text style={styles.muteIcon}>🔕</Text>}
        {selectedChan && (
          <TouchableOpacity onPress={() => setActionsFor(selectedChan)} style={styles.headerActions}>
            <Text style={styles.headerActionsTxt}>⋯</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Messages */}
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
        keyboardVerticalOffset={80}
      >
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(m) => m._id}
          renderItem={({ item }) => (
            item.is_system ? (
              <View testID={`chat-message-${item._id}`} style={styles.systemBubble}>
                <Text style={styles.systemTxt}>{item.content}</Text>
              </View>
            ) : (
              <View testID={`chat-message-${item._id}`} style={styles.msgRow}>
                <View style={styles.avatar}><Text style={styles.avatarTxt}>{initialsFor(item.sender_name)}</Text></View>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 6 }}>
                    <Text style={styles.sender}>{item.sender_name}</Text>
                    <Text style={styles.timestamp}>{fmtTime(item.created_at)}</Text>
                  </View>
                  <Text style={styles.msgTxt}>{item.content}</Text>
                </View>
              </View>
            )
          )}
          contentContainerStyle={{ padding: 12, gap: 10 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
          ListEmptyComponent={!loading && (
            <Text style={{ color: COLORS.muted, textAlign: 'center', marginTop: 32 }}>
              {selectedChan ? 'No messages yet — say hi 👋' : 'Pick a channel to start chatting'}
            </Text>
          )}
        />
        {loading && <ActivityIndicator color={COLORS.primary} style={{ marginVertical: 8 }} />}

        {/* @mention popup */}
        {mentionOpen && filteredMentions.length > 0 && (
          <View style={styles.mentionPopup} testID="chat-mention-popup">
            {filteredMentions.map((m) => (
              <TouchableOpacity
                key={m.team_id}
                testID={`chat-mention-option-${m.team_id}`}
                onPress={() => insertMention(m.team_name)}
                style={styles.mentionRow}
              >
                <View style={styles.avatarSm}><Text style={styles.avatarSmTxt}>{m.abbr}</Text></View>
                <Text style={styles.mentionName}>{m.team_name}</Text>
                <Text style={styles.mentionOwner}>{m.owner_name}</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        <View style={styles.inputBar}>
          <TextInput
            testID="chat-message-input"
            style={styles.input}
            value={draft}
            onChangeText={handleDraftChange}
            placeholder={selectedChan ? `Message ${selectedChan.kind === 'dm' ? selectedChan.name : '#' + selectedChan.name}` : 'Pick a channel'}
            placeholderTextColor={COLORS.muted}
            editable={!!selectedChan}
            multiline
          />
          <TouchableOpacity
            testID="chat-send-btn"
            disabled={!selectedChan || !draft.trim()}
            onPress={send}
            style={[styles.sendBtn, (!selectedChan || !draft.trim()) && { opacity: 0.4 }]}
          >
            <Text style={styles.sendTxt}>Send</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>

      {/* Channel actions modal (mute / delete) */}
      <Modal visible={!!actionsFor} transparent animationType="fade" onRequestClose={() => setActionsFor(null)}>
        <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={() => setActionsFor(null)}>
          <View style={styles.actionSheet}>
            <Text style={styles.actionTitle}>
              {actionsFor?.kind === 'dm' ? actionsFor.name : `#${actionsFor?.name || ''}`}
            </Text>
            <Text style={styles.actionLabel}>{actionsFor?.muted ? 'Already muted' : 'Mute notifications'}</Text>
            {MUTE_DURATIONS.map((opt) => (
              <TouchableOpacity
                key={opt.value}
                testID={`chat-mute-${actionsFor?._id}-${opt.value}`}
                onPress={() => handleMute(actionsFor._id, opt.value)}
                style={styles.actionBtn}
              >
                <Text style={styles.actionTxt}>🔕  {opt.label}</Text>
              </TouchableOpacity>
            ))}
            {actionsFor?.muted && (
              <TouchableOpacity
                testID={`chat-unmute-${actionsFor?._id}`}
                onPress={() => handleMute(actionsFor._id, null)}
                style={styles.actionBtn}
              >
                <Text style={styles.actionTxt}>🔔  Unmute</Text>
              </TouchableOpacity>
            )}
            {isCommish && actionsFor?.kind === 'channel' && !actionsFor?.is_default && (
              <TouchableOpacity
                testID={`chat-delete-${actionsFor?._id}`}
                onPress={() => handleDeleteChannel(actionsFor)}
                style={styles.actionBtn}
              >
                <Text style={[styles.actionTxt, { color: COLORS.danger }]}>🗑  Delete channel</Text>
              </TouchableOpacity>
            )}
          </View>
        </TouchableOpacity>
      </Modal>

      {/* Create channel modal */}
      <Modal visible={createOpen} transparent animationType="fade" onRequestClose={() => setCreateOpen(false)}>
        <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={() => setCreateOpen(false)}>
          <View style={styles.actionSheet} onStartShouldSetResponder={() => true}>
            <Text style={styles.actionTitle}>Create channel</Text>
            <Text style={[styles.actionLabel, { color: COLORS.muted, marginBottom: 8 }]}>
              Lowercase letters, numbers, hyphens. Up to {maxChannels} channels per league.
            </Text>
            <TextInput
              testID="chat-new-channel-input"
              style={[styles.input, { marginBottom: 12 }]}
              value={newName}
              onChangeText={setNewName}
              placeholder="e.g. waivers-talk"
              placeholderTextColor={COLORS.muted}
              maxLength={32}
              autoCapitalize="none"
            />
            <TouchableOpacity
              testID="chat-new-channel-submit"
              onPress={handleCreate}
              disabled={!newName.trim()}
              style={[styles.sendBtn, !newName.trim() && { opacity: 0.4 }, { alignSelf: 'flex-end' }]}
            >
              <Text style={styles.sendTxt}>Create</Text>
            </TouchableOpacity>
          </View>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  sidebar: {
    paddingTop: 8, paddingBottom: 8,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: COLORS.border,
  },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 14, marginBottom: 6 },
  sectionTitle: { color: COLORS.muted, fontSize: 11, letterSpacing: 1.2, fontWeight: '600' },
  cap: { color: COLORS.muted, fontSize: 10 },
  newBtn: { width: 22, height: 22, borderRadius: 4, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center' },
  newBtnTxt: { color: COLORS.primary, fontSize: 16, fontWeight: '600' },
  chanRow: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 12, paddingVertical: 8,
    backgroundColor: COLORS.card, borderRadius: 14,
    minWidth: 110, maxWidth: 220,
  },
  chanRowActive: { backgroundColor: 'rgba(0, 210, 255, 0.12)' },
  chanIcon: { color: COLORS.muted, fontSize: 12, fontWeight: '600' },
  chanName: { color: COLORS.text, fontSize: 13, flex: 1 },
  muteIcon: { fontSize: 11 },
  unreadPill: {
    minWidth: 18, height: 18, paddingHorizontal: 5, borderRadius: 9,
    backgroundColor: COLORS.danger, alignItems: 'center', justifyContent: 'center',
  },
  unreadTxt: { color: '#fff', fontSize: 10, fontWeight: '700' },
  activeHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: 14, paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: COLORS.border,
  },
  activeName: { color: COLORS.text, fontSize: 16, fontWeight: '600', flex: 1 },
  headerActions: { padding: 6 },
  headerActionsTxt: { color: COLORS.muted, fontSize: 18 },
  msgRow: { flexDirection: 'row', gap: 10 },
  avatar: { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center' },
  avatarTxt: { color: COLORS.text, fontWeight: '600', fontSize: 12 },
  avatarSm: { width: 22, height: 22, borderRadius: 11, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center' },
  avatarSmTxt: { color: COLORS.text, fontWeight: '600', fontSize: 10 },
  sender: { color: COLORS.text, fontSize: 13, fontWeight: '600' },
  timestamp: { color: COLORS.muted, fontSize: 11 },
  msgTxt: { color: 'rgba(255,255,255,0.85)', fontSize: 14, marginTop: 2 },
  systemBubble: {
    alignSelf: 'center', maxWidth: '85%',
    backgroundColor: 'rgba(255, 184, 0, 0.1)', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 12,
  },
  systemTxt: { color: COLORS.accent, fontSize: 13 },
  inputBar: {
    flexDirection: 'row', gap: 8, padding: 10,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: COLORS.border,
    backgroundColor: COLORS.bg,
  },
  input: {
    flex: 1, backgroundColor: COLORS.card, borderRadius: 18,
    paddingHorizontal: 14, paddingVertical: 10, color: COLORS.text, fontSize: 14,
    maxHeight: 120,
  },
  sendBtn: { backgroundColor: COLORS.primary, borderRadius: 18, paddingHorizontal: 16, paddingVertical: 10, alignItems: 'center', justifyContent: 'center' },
  sendTxt: { color: COLORS.bg, fontWeight: '700', fontSize: 13 },
  mentionPopup: {
    position: 'absolute', left: 8, right: 8, bottom: 70,
    backgroundColor: COLORS.card, borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth, borderColor: COLORS.border,
    overflow: 'hidden', zIndex: 10,
  },
  mentionRow: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10 },
  mentionName: { color: COLORS.text, fontWeight: '600', fontSize: 13 },
  mentionOwner: { color: COLORS.muted, fontSize: 11 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'flex-end' },
  actionSheet: {
    backgroundColor: COLORS.card, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 22,
    borderTopLeftRadius: 16, borderTopRightRadius: 16,
  },
  actionTitle: { color: COLORS.text, fontSize: 15, fontWeight: '700', marginBottom: 4 },
  actionLabel: { color: COLORS.muted, fontSize: 11, marginBottom: 6, marginTop: 6 },
  actionBtn: { paddingVertical: 10 },
  actionTxt: { color: COLORS.text, fontSize: 14 },
});
