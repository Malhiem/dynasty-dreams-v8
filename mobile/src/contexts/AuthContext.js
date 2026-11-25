import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api, { setTokens, clearTokens, getAccessToken, setAuthLostHandler } from '../lib/api';
import { resetSocket } from '../lib/socket';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const token = await getAccessToken();
      if (!token) { setUser(null); setLoading(false); return; }
      const { data } = await api.get('/auth/me');
      setUser(data);
    } catch (e) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);

  // When the session can no longer be refreshed, return to the login screen.
  useEffect(() => {
    setAuthLostHandler(() => { resetSocket(); setUser(null); });
    return () => setAuthLostHandler(null);
  }, []);

  const login = async (email, password) => {
    const { data } = await api.post('/auth/login', { email, password });
    if (data.access_token) await setTokens(data.access_token, data.refresh_token);
    resetSocket();
    setUser(data);
    return data;
  };

  const register = async (email, password, name) => {
    const { data } = await api.post('/auth/register', { email, password, name });
    if (data.access_token) await setTokens(data.access_token, data.refresh_token);
    resetSocket();
    setUser(data);
    return data;
  };

  const logout = async () => {
    try { await api.post('/auth/logout'); } catch (e) {}
    await clearTokens();
    resetSocket();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
