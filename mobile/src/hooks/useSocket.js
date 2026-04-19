import { useEffect, useRef, useState, useCallback } from 'react';
import { io } from 'socket.io-client';

const API_BASE_URL = 'https://your-dynasty-dreams-api.com';

let socketInstance = null;

function getSocket() {
  if (!socketInstance) {
    socketInstance = io(API_BASE_URL, {
      path: '/api/socket.io',
      transports: ['websocket'],
      autoConnect: false,
    });
  }
  return socketInstance;
}

export function useSocket(roomId, handlers = {}, userId = null) {
  const [connected, setConnected] = useState(false);
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    if (!roomId) return;
    const socket = getSocket();

    const onConnect = () => {
      setConnected(true);
      socket.emit('join_room', { room_id: roomId, user_id: userId });
    };
    const onDisconnect = () => setConnected(false);

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    if (socket.connected) onConnect();
    else socket.connect();

    const eventNames = Object.keys(handlersRef.current);
    eventNames.forEach(event => {
      socket.on(event, (data) => handlersRef.current[event]?.(data));
    });

    return () => {
      socket.emit('leave_room', { room_id: roomId });
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      eventNames.forEach(event => socket.off(event));
    };
  }, [roomId, userId]);

  const emit = useCallback((event, data) => {
    const socket = getSocket();
    if (socket.connected) socket.emit(event, data);
  }, []);

  return { connected, emit };
}

export function useDraftSocket(draftId, callbacks = {}) {
  return useSocket(draftId ? `draft_${draftId}` : null, {
    draft_started: callbacks.onDraftStarted,
    draft_pick: callbacks.onDraftPick,
    draft_chat: callbacks.onChatMessage,
    draft_timer_toggle: callbacks.onTimerToggle,
    draft_completed: callbacks.onDraftCompleted,
    auction_nomination: callbacks.onAuctionNomination,
    auction_bid: callbacks.onAuctionBid,
    auction_resolved: callbacks.onAuctionResolved,
  }, callbacks.userId);
}

export function useLeagueSocket(leagueId, callbacks = {}) {
  return useSocket(leagueId ? `league_${leagueId}` : null, {
    trade_proposed: callbacks.onTradeProposed,
    trade_accepted: callbacks.onTradeAccepted,
    waivers_processed: callbacks.onWaiversProcessed,
    week_simulated: callbacks.onWeekSimulated,
    activity_feed: callbacks.onActivityFeed,
    notification: callbacks.onNotification,
  }, callbacks.userId);
}
