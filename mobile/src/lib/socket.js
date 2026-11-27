import { io } from 'socket.io-client';
import { BACKEND_URL, getFreshAccessToken } from './api';

// The server refuses any socket handshake that has no valid access token
// (`auth: { token }` or a Bearer header), so the token is supplied through the
// `auth` callback: it runs on every (re)connect and always returns a fresh one.
let socketInstance = null;

export function socketAuth(cb) {
  getFreshAccessToken()
    .then((token) => cb({ token: token || '' }))
    .catch(() => cb({ token: '' }));
}

export function getSocket() {
  if (!socketInstance) {
    socketInstance = io(BACKEND_URL, {
      path: '/api/socket.io',
      transports: ['websocket'],
      autoConnect: false,
      auth: socketAuth,
    });
  }
  return socketInstance;
}

// Drop the connection when the signed-in user changes (login, logout, session
// lost) so the next connect carries the new user's token and rooms.
export function resetSocket() {
  if (socketInstance) {
    socketInstance.removeAllListeners();
    socketInstance.disconnect();
    socketInstance = null;
  }
}
