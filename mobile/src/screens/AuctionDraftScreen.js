import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, TextInput, TouchableOpacity, StyleSheet, SafeAreaView } from 'react-native';
import api from '../lib/api';
import { useDraftSocket } from '../hooks/useSocket';
import { useAuth } from '../contexts/AuthContext';

export default function AuctionDraftScreen({ route }) {
  const draftId = route?.params?.draftId;
  const { user } = useAuth();
  const [draft, setDraft] = useState(null);
  const [auctionState, setAuctionState] = useState(null);
  const [players, setPlayers] = useState([]);
  const [search, setSearch] = useState('');
  const [bidAmount, setBidAmount] = useState('1');

  const fetchAll = async () => {
    if (!draftId) return;
    try {
      const [d, a, p] = await Promise.all([
        api.get(`/drafts/${draftId}`),
        api.get(`/drafts/${draftId}/auction/state`),
        api.get(`/drafts/${draftId}/eligible-players?limit=20${search ? `&search=${search}` : ''}`),
      ]);
      setDraft(d.data);
      setAuctionState(a.data);
      setPlayers(p.data.players || []);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { fetchAll(); }, [draftId]);
  useEffect(() => { const t = setTimeout(fetchAll, 300); return () => clearTimeout(t); }, [search]);
  useEffect(() => { if (!draftId) return; const i = setInterval(fetchAll, 3000); return () => clearInterval(i); }, [draftId]);

  const { connected } = useDraftSocket(draftId, {
    userId: user?.id,
    onAuctionBid: fetchAll,
    onAuctionResolved: fetchAll,
    onDraftPick: fetchAll,
  });

  const handleNominate = async (pid) => { try { await api.post(`/drafts/${draftId}/auction/nominate`, { player_id: pid, opening_bid: 1 }); fetchAll(); } catch (e) { alert(e.response?.data?.detail); } };
  const handleBid = async () => { try { await api.post(`/drafts/${draftId}/auction/bid`, { amount: parseFloat(bidAmount) }); fetchAll(); } catch (e) { alert(e.response?.data?.detail); } };

  const auction = auctionState?.active_auction;
  const budgets = auctionState?.budgets || [];

  return (
    <SafeAreaView style={s.container}>
      <ScrollView>
        <View style={s.header}>
          <Text style={s.title}>AUCTION DRAFT</Text>
          <View style={s.statusRow}>
            <View style={[s.dot, { backgroundColor: connected ? '#34C759' : '#FF3B30' }]} />
            <Text style={s.statusText}>{(draft?.picks || []).length} picks · {budgets.length} teams</Text>
          </View>
        </View>

        {/* Active Auction */}
        {auction ? (
          <View style={s.auctionCard}>
            <Text style={s.auctionLabel}>NOW BIDDING</Text>
            <Text style={s.auctionPlayer}>{auction.player_name}</Text>
            <Text style={s.auctionMeta}>{auction.player_position} · {auction.player_team}</Text>
            <Text style={s.currentBid}>${auction.current_bid}</Text>
            <Text style={s.bidder}>{auction.current_bidder_team_name}</Text>
            <View style={s.bidRow}>
              <TextInput style={s.bidInput} keyboardType="numeric" value={bidAmount} onChangeText={setBidAmount} />
              <TouchableOpacity style={s.bidBtn} onPress={handleBid}><Text style={s.bidBtnText}>Bid</Text></TouchableOpacity>
            </View>
            <View style={s.quickBids}>{[1, 5, 10, 25].map(n => (
              <TouchableOpacity key={n} style={s.quickBtn} onPress={() => setBidAmount(String(auction.current_bid + n))}>
                <Text style={s.quickBtnText}>+${n}</Text>
              </TouchableOpacity>
            ))}</View>
          </View>
        ) : (
          <View style={s.noAuction}><Text style={s.noAuctionText}>No active auction — nominate a player</Text></View>
        )}

        {/* Budgets */}
        <View style={s.section}><Text style={s.sectionTitle}>TEAM BUDGETS</Text>
          {budgets.map(b => (
            <View key={b.team_id} style={s.budgetRow}>
              <Text style={s.budgetTeam}>{b.team_name}</Text>
              <Text style={[s.budgetVal, b.budget_remaining < 20 && s.danger]}>${b.budget_remaining}</Text>
            </View>
          ))}
        </View>

        {/* Players */}
        <View style={s.section}><Text style={s.sectionTitle}>NOMINATE PLAYER</Text>
          <TextInput style={s.searchInput} placeholder="Search..." placeholderTextColor="#52525B" value={search} onChangeText={setSearch} />
          {players.slice(0, 10).map(p => (
            <TouchableOpacity key={p.id} style={s.playerRow} onPress={() => !auction && handleNominate(p.id)}>
              <Text style={s.playerPos}>{p.position}</Text>
              <View style={s.info}><Text style={s.playerName}>{p.name}</Text><Text style={s.playerMeta}>{p.nhlTeam} · {p.pts}P</Text></View>
              {!auction && <Text style={s.nominateText}>Nominate</Text>}
            </TouchableOpacity>
          ))}
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
  dot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { color: '#A1A1AA', fontSize: 12 },
  auctionCard: { margin: 16, backgroundColor: '#141414', borderRadius: 12, padding: 20, alignItems: 'center', borderWidth: 2, borderColor: '#00D2FF50' },
  auctionLabel: { color: '#00D2FF', fontSize: 10, fontWeight: '700', letterSpacing: 2 },
  auctionPlayer: { fontSize: 22, fontWeight: '800', color: '#fff', marginTop: 8 },
  auctionMeta: { color: '#A1A1AA', fontSize: 13 },
  currentBid: { fontSize: 44, fontWeight: '900', color: '#00D2FF', marginTop: 12 },
  bidder: { color: '#A1A1AA', fontSize: 13 },
  bidRow: { flexDirection: 'row', gap: 8, marginTop: 16, width: '100%' },
  bidInput: { flex: 1, backgroundColor: '#1A1A1A', borderRadius: 8, padding: 12, color: '#fff', fontSize: 18, textAlign: 'center' },
  bidBtn: { backgroundColor: '#00D2FF', borderRadius: 8, paddingHorizontal: 24, justifyContent: 'center' },
  bidBtnText: { color: '#000', fontSize: 16, fontWeight: '800' },
  quickBids: { flexDirection: 'row', gap: 8, marginTop: 8 },
  quickBtn: { flex: 1, backgroundColor: '#1A1A1A', borderRadius: 6, padding: 8, alignItems: 'center' },
  quickBtnText: { color: '#fff', fontSize: 12, fontWeight: '600' },
  noAuction: { margin: 16, padding: 30, backgroundColor: '#141414', borderRadius: 12, alignItems: 'center' },
  noAuctionText: { color: '#A1A1AA' },
  section: { padding: 16 },
  sectionTitle: { fontSize: 12, fontWeight: '700', color: '#A1A1AA', letterSpacing: 1, marginBottom: 10 },
  budgetRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)' },
  budgetTeam: { color: '#fff', fontSize: 13 },
  budgetVal: { color: '#34C759', fontSize: 14, fontWeight: '700' },
  danger: { color: '#FF3B30' },
  searchInput: { backgroundColor: '#141414', borderRadius: 8, padding: 10, color: '#fff', marginBottom: 10 },
  playerRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.05)' },
  playerPos: { color: '#00D2FF', fontSize: 11, fontWeight: '700', width: 30 },
  info: { flex: 1 },
  playerName: { color: '#fff', fontSize: 13, fontWeight: '600' },
  playerMeta: { color: '#A1A1AA', fontSize: 10 },
  nominateText: { color: '#00D2FF', fontSize: 11, fontWeight: '600' },
});
