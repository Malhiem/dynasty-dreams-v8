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
      // Iter 230q — SEC-001 made the socket auth handshake mandatory.
      // The server reads the access_token from the httpOnly cookie set
      // at login, but cookies only flow on a WS handshake when the
      // socket.io client opts in to credentials.
      withCredentials: true,
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
 * Also tracks presence (which user_ids are currently in the draft room).
 */
export function useDraftSocket(draftId, callbacks = {}) {
  const [onlineUserIds, setOnlineUserIds] = useState(new Set());

  const socketState = useSocket(
    draftId ? `draft_${draftId}` : null,
    {
      draft_started: callbacks.onDraftStarted,
      draft_pick: callbacks.onDraftPick,
      draft_chat: callbacks.onChatMessage,
      draft_timer_toggle: callbacks.onTimerToggle,
      draft_config_updated: callbacks.onConfigUpdated,
      draft_completed: callbacks.onDraftCompleted,
      // Iter 140 — presence
      presence_state: (data) => {
        if (!data) return;
        setOnlineUserIds(new Set((data.user_ids || []).map(String)));
      },
      user_joined: (data) => {
        if (data?.user_id) {
          setOnlineUserIds((prev) => {
            const next = new Set(prev);
            next.add(String(data.user_id));
            return next;
          });
        }
        callbacks.onUserJoined?.(data);
      },
      user_left: (data) => {
        if (data?.user_id) {
          setOnlineUserIds((prev) => {
            const next = new Set(prev);
            next.delete(String(data.user_id));
            return next;
          });
        }
        callbacks.onUserLeft?.(data);
      },
    },
    callbacks.userId
  );

  // Reset presence on draft change / unmount
  useEffect(() => {
    if (!draftId) setOnlineUserIds(new Set());
  }, [draftId]);

  return { ...socketState, onlineUserIds };
}

/**
 * Hook for league-level WebSocket events.
 *
 * Iter 232b — also tracks live presence (which user_ids are currently
 * connected to this league's socket room). Surfaces `onlineUserIds`
 * so the League Chat (and any future league-scoped surface) can show
 * a "who's online" indicator. Powered by the server's existing
 * `presence_state` / `user_joined` / `user_left` events emitted on
 * every connect/join/leave to the room.
 */
export function useLeagueSocket(leagueId, callbacks = {}) {
  const [onlineUserIds, setOnlineUserIds] = useState(new Set());

  const socketState = useSocket(
    leagueId ? `league_${leagueId}` : null,
    {
      trade_proposed: callbacks.onTradeProposed,
      trade_accepted: callbacks.onTradeAccepted,
      trade_vetoed: callbacks.onTradeVetoed,
      waivers_processed: callbacks.onWaiversProcessed,
      week_simulated: callbacks.onWeekSimulated,
      // Iter 232b — presence
      presence_state: (data) => {
        if (!data) return;
        setOnlineUserIds(new Set((data.user_ids || []).map(String)));
      },
      user_joined: (data) => {
        if (data?.user_id) {
          setOnlineUserIds((prev) => {
            const next = new Set(prev);
            next.add(String(data.user_id));
            return next;
          });
        }
        callbacks.onUserJoined?.(data);
      },
      user_left: (data) => {
        if (data?.user_id) {
          setOnlineUserIds((prev) => {
            const next = new Set(prev);
            next.delete(String(data.user_id));
            return next;
          });
        }
        callbacks.onUserLeft?.(data);
      },
    },
    callbacks.userId
  );

  // Reset presence on league change / unmount so users don't carry
  // "online" markers between leagues.
  useEffect(() => {
    if (!leagueId) setOnlineUserIds(new Set());
  }, [leagueId]);

  return { ...socketState, onlineUserIds };
}
