import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const api = axios.create({
  baseURL: `${BACKEND_URL}/api`,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json'
  }
});

// De-duplicate concurrent refresh calls — if multiple requests 401 in parallel,
// only issue one /auth/refresh and share the result.
let refreshPromise = null;

function refreshOnce() {
  if (!refreshPromise) {
    refreshPromise = axios
      .post(`${BACKEND_URL}/api/auth/refresh`, {}, { withCredentials: true })
      .finally(() => {
        // Release the promise after a tick so follow-up 401s can retry fresh
        setTimeout(() => { refreshPromise = null; }, 0);
      });
  }
  return refreshPromise;
}

// Response interceptor for token refresh.
// IMPORTANT: We DO NOT hard-redirect on refresh failure. That caused a race
// where multiple concurrent 401s would boot the user back to /login right
// after a successful sign-in. Instead, we dispatch a custom `auth-expired`
// event that AuthContext listens to and clears user state, allowing
// ProtectedRoute to handle navigation cleanly.
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (!originalRequest) return Promise.reject(error);

    // Never try to refresh the refresh endpoint itself
    const isRefreshCall = originalRequest.url && originalRequest.url.includes('/auth/refresh');
    if (error.response?.status === 401 && !originalRequest._retry && !isRefreshCall) {
      originalRequest._retry = true;
      try {
        await refreshOnce();
        return api(originalRequest);
      } catch (e) {
        // Refresh failed — broadcast so AuthContext can clear user state
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('auth-expired'));
        }
        return Promise.reject(e);
      }
    }
    return Promise.reject(error);
  }
);

// Format API errors
export function formatApiError(error) {
  const detail = error.response?.data?.detail;
  if (detail == null) return 'Something went wrong. Please try again.';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => (e && typeof e.msg === 'string' ? e.msg : JSON.stringify(e))).filter(Boolean).join(' ');
  }
  if (detail && typeof detail.msg === 'string') return detail.msg;
  return String(detail);
}

export default api;
