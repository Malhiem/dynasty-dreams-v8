import { useEffect, useRef, useState } from 'react';
import { io } from 'socket.io-client';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Global Socket.IO event listener (no room join required).
 * Listens to server-side broadcasts such as `live_scoring_update`.
 */
export function useGlobalSocketEvent(eventName, handler) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!eventName) return undefined;
    const socket = io(BACKEND_URL, {
      path: '/api/socket.io',
      transports: ['websocket', 'polling'],
    });
    const onConnect = () => setConnected(true);
    const onDisconnect = () => setConnected(false);
    const onEvent = (payload) => handlerRef.current && handlerRef.current(payload);

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    socket.on(eventName, onEvent);

    return () => {
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      socket.off(eventName, onEvent);
      socket.disconnect();
    };
  }, [eventName]);

  return { connected };
}
