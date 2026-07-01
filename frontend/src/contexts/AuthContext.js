import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking, false = not auth, object = authed
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const { data } = await axios.get(`${BACKEND_URL}/api/auth/me`, {
        withCredentials: true
      });
      setUser(data);
    } catch (e) {
      setUser(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  // Listen for auth-expired events dispatched by the axios interceptor.
  // This replaces the previous hard-redirect behaviour and prevents race
  // conditions where concurrent 401s right after login would bounce the
  // user back to /login.
  useEffect(() => {
    const onExpired = () => setUser(false);
    window.addEventListener('auth-expired', onExpired);
    return () => window.removeEventListener('auth-expired', onExpired);
  }, []);

  const login = async (email, password) => {
    // Iter 207 — include a device fingerprint hash so the backend can
    // log it into user_login_audit for multi-account detection.
    let device_hash = null;
    try {
      const { getDeviceHash } = await import("@/lib/device-hash");
      device_hash = await getDeviceHash();
    } catch { /* non-fatal */ }
    const { data } = await axios.post(`${BACKEND_URL}/api/auth/login`,
      { email, password, device_hash },
      { withCredentials: true }
    );
    setUser(data);
    return data;
  };

  const register = async (email, password, username) => {
    const { data } = await axios.post(`${BACKEND_URL}/api/auth/register`,
      { email, password, username },
      { withCredentials: true }
    );
    setUser(data);
    return data;
  };

  const logout = async () => {
    await axios.post(`${BACKEND_URL}/api/auth/logout`, {}, { withCredentials: true });
    try { localStorage.removeItem('auth_remember'); } catch { /* noop */ }
    // SEC-003 (iter 232h) — Tell the service worker to purge the API
    // cache so a shared-device next-user can't see this user's cached
    // league / standings / matchup data on the login screen before
    // their own network fetch completes. Message is fire-and-forget;
    // browsers without an active SW registration silently no-op.
    try {
      if (navigator?.serviceWorker?.controller) {
        navigator.serviceWorker.controller.postMessage({ type: 'PURGE_API_CACHE' });
      }
    } catch { /* noop — old browsers / privacy mode */ }
    setUser(false);
  };

  const refreshToken = async () => {
    try {
      await axios.post(`${BACKEND_URL}/api/auth/refresh`, {}, { withCredentials: true });
      await checkAuth();
    } catch (e) {
      setUser(false);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshToken, checkAuth, refreshUser: checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
