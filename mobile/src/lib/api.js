import axios from 'axios';
import * as SecureStore from 'expo-secure-store';

// Backend base URL — set EXPO_PUBLIC_BACKEND_URL in /app/mobile/.env
const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL;
if (!BACKEND_URL) {
  console.warn('[api] EXPO_PUBLIC_BACKEND_URL is not set. Mobile API calls will fail.');
}
const API_BASE_URL = `${BACKEND_URL || ''}/api`;
export { BACKEND_URL, API_BASE_URL };

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

// Token management
let accessToken = null;

export async function setTokens(access, refresh) {
  accessToken = access;
  await SecureStore.setItemAsync('access_token', access);
  await SecureStore.setItemAsync('refresh_token', refresh);
}

export async function getAccessToken() {
  if (accessToken) return accessToken;
  accessToken = await SecureStore.getItemAsync('access_token');
  return accessToken;
}

export async function clearTokens() {
  accessToken = null;
  await SecureStore.deleteItemAsync('access_token');
  await SecureStore.deleteItemAsync('refresh_token');
}

// Request interceptor - attach token
api.interceptors.request.use(async (config) => {
  const token = await getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Called when the session can no longer be refreshed (refresh token missing,
// expired or revoked). AuthContext registers a handler that signs the user out
// so the app returns to the login screen instead of failing silently.
let authLostHandler = null;
export function setAuthLostHandler(fn) {
  authLostHandler = fn;
}

// One refresh at a time: concurrent 401s (or a socket handshake) share it.
let refreshInFlight = null;
export function refreshSession() {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const refreshToken = await SecureStore.getItemAsync('refresh_token');
      if (!refreshToken) throw new Error('no refresh token');
      const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, {}, {
        headers: { Authorization: `Bearer ${refreshToken}` },
        timeout: 15000,
      });
      await setTokens(data.access_token, data.refresh_token);
      return data.access_token;
    })().finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

async function signOutLocally() {
  await clearTokens();
  if (authLostHandler) authLostHandler();
}

// Seconds until the JWT expires (negative once expired); null if unreadable.
export function secondsUntilExpiry(token) {
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(globalThis.atob(part + '='.repeat((4 - (part.length % 4)) % 4)));
    return typeof payload.exp === 'number' ? payload.exp - Date.now() / 1000 : null;
  } catch (e) {
    return null;
  }
}

// An access token that is valid now: refreshes first when it is expired or about
// to expire. Used for the socket handshake, which cannot retry on a 401.
export async function getFreshAccessToken() {
  const token = await getAccessToken();
  if (!token) return null;
  const left = secondsUntilExpiry(token);
  if (left !== null && left > 30) return token;
  try {
    return await refreshSession();
  } catch (e) {
    return left !== null && left > 0 ? token : null;
  }
}

// Response interceptor - handle token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        await refreshSession();
      } catch (e) {
        await signOutLocally();
        return Promise.reject(error);
      }
      return api(originalRequest);
    }
    return Promise.reject(error);
  }
);

export default api;
