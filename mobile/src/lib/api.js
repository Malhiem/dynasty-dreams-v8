import axios from 'axios';
import * as SecureStore from 'expo-secure-store';

// Update this to your production API URL
const API_BASE_URL = 'https://your-dynasty-dreams-api.com/api';

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

// Response interceptor - handle token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const refreshToken = await SecureStore.getItemAsync('refresh_token');
        const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, {}, {
          headers: { Authorization: `Bearer ${refreshToken}` }
        });
        await setTokens(data.access_token, data.refresh_token);
        return api(originalRequest);
      } catch (e) {
        await clearTokens();
        // Navigate to login - handled by AuthContext
      }
    }
    return Promise.reject(error);
  }
);

export default api;
