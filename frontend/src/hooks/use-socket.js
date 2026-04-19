import { useEffect, useRef, useState, useCallback } from 'react';
import { io } from 'socket.io-client';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

// Singleton socket instance
let socketInstance = null;

function getSocket() {
  if (!socketInstance) {
    socketInstance = io(BACKEND_URL, {
      path: '/api/socket.io',
      transports: ['websocket', 'polling'],
      autoConnect: false,
    });
  }
  return socketInstance;
}

/**
 * Hook to manage Socket.IO connection and room subscriptions.
 * @param {string} roomId - Room to join (e.g., "draft_abc123" or "league_xyz")
 * @param {Object} handlers - Map of event name → callback function
 * @param {string} userId - Current user ID
 */
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

    const onDisconnect = () => {
      setConnected(false);
    };

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);

    // If already connected, join room immediately
    if (socket.connected) {
      onConnect();
    } else {
      socket.connect();
    }

    // Register all event handlers
    const eventNames = Object.keys(handlersRef.current);
    const wrappedHandlers = {};
    eventNames.forEach(event => {
      wrappedHandlers[event] = (data) => {
        if (handlersRef.current[event]) {
          handlersRef.current[event](data);
        }
      };
      socket.on(event, wrappedHandlers[event]);
    });

    return () => {
      socket.emit('leave_room', { room_id: roomId });
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      eventNames.forEach(event => {
        socket.off(event, wrappedHandlers[event]);
      });
    };
  }, [roomId, userId]);

  // Re-register handlers when they change
  useEffect(() => {
    const socket = getSocket();
    const eventNames = Object.keys(handlers);
    const wrappedHandlers = {};

    eventNames.forEach(event => {
      wrappedHandlers[event] = (data) => {
        if (handlersRef.current[event]) {
          handlersRef.current[event](data);
        }
      };
      socket.on(event, wrappedHandlers[event]);
    });

    return () => {
      eventNames.forEach(event => {
        socket.off(event, wrappedHandlers[event]);
      });
    };
  }, [Object.keys(handlers).join(',')]);

  const emit = useCallback((event, data) => {
    const socket = getSocket();
    if (socket.connected) {
      socket.emit(event, data);
    }
  }, []);

  return { connected, emit };
}

/**
 * Hook for draft room WebSocket events.
 */
export function useDraftSocket(draftId, callbacks = {}) {
  return useSocket(
    draftId ? `draft_${draftId}` : null,
    {
      draft_started: callbacks.onDraftStarted,
      draft_pick: callbacks.onDraftPick,
      draft_chat: callbacks.onChatMessage,
      draft_timer_toggle: callbacks.onTimerToggle,
      draft_config_updated: callbacks.onConfigUpdated,
      draft_completed: callbacks.onDraftCompleted,
      user_joined: callbacks.onUserJoined,
    },
    callbacks.userId
  );
}

/**
 * Hook for league-level WebSocket events.
 */
export function useLeagueSocket(leagueId, callbacks = {}) {
  return useSocket(
    leagueId ? `league_${leagueId}` : null,
    {
      trade_proposed: callbacks.onTradeProposed,
      trade_accepted: callbacks.onTradeAccepted,
      trade_vetoed: callbacks.onTradeVetoed,
      waivers_processed: callbacks.onWaiversProcessed,
      week_simulated: callbacks.onWeekSimulated,
    },
    callbacks.userId
  );
}
