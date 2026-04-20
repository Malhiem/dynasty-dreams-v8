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
    const { data } = await axios.post(`${BACKEND_URL}/api/auth/login`, 
      { email, password },
      { withCredentials: true }
    );
    setUser(data);
    return data;
  };

  const register = async (email, password, name) => {
    const { data } = await axios.post(`${BACKEND_URL}/api/auth/register`,
      { email, password, name },
      { withCredentials: true }
    );
    setUser(data);
    return data;
  };

  const logout = async () => {
    await axios.post(`${BACKEND_URL}/api/auth/logout`, {}, { withCredentials: true });
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
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshToken, checkAuth }}>
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
