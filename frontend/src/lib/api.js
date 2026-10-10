import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const api = axios.create({
  baseURL: `${BACKEND_URL}/api`,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json'
  }
});

// ─── Iter 148 — GET request dedupe + short-lived cache ────────────────────
// Several pages mount in parallel (sidebar + page header + content) and fire
// the same `GET /leagues?my_leagues=true` or `GET /teams?league_id=…` request
// 3-5x within a few hundred ms. That used to trigger 429 bursts from the
// rate limiter. We collapse identical in-flight GETs into one promise and
// cache the response body for `CACHE_TTL_MS` so rapid re-mounts hit cache.
let cacheEpoch = 0;
const INFLIGHT_GETS = new Map();      // key → Promise<AxiosResponse>
const GET_CACHE = new Map();          // key → { ts, data, status, headers }
const CACHE_TTL_MS = 30_000;
// Iter 194 — Some endpoints (the user's own league list) must stay
// snappy when a new league is created/joined elsewhere; we shorten
// their TTL aggressively so the dashboard + global league switcher
// pick up new memberships within 5 s instead of 30 s.
const SHORT_TTL_PATTERNS = [
  /\/leagues\?my_leagues=true/,
];
const SHORT_TTL_MS = 5_000;
const DEDUPABLE_PATTERNS = [
  /\/teams\/mine\/summaries$/,
  /\/leagues\?my_leagues=true/,
  /\/teams\?league_id=[^&]+$/,

];
function _isDedupableGetUrl(url) {
  if (!url) return false;
  return DEDUPABLE_PATTERNS.some((re) => re.test(url));
}
function _cacheKey(config) {
  // Use the fully-resolved URL (baseURL + url + params) so requests with
  // different `?league_id=X` are bucketed independently.
  const base = config.baseURL || '';
  let u = (config.url || '').startsWith('http')
    ? config.url
    : `${base}${config.url || ''}`;
  if (config.params) {
    const qs = new URLSearchParams(config.params).toString();
    if (qs) u += (u.includes('?') ? '&' : '?') + qs;
  }
  return u;
}
// Invalidate the cache when external code mutates (e.g. new league created).
export function invalidateApiCache(pattern) {
  if (!pattern) { cacheEpoch += 1; GET_CACHE.clear(); INFLIGHT_GETS.clear(); return; }
  const re = pattern instanceof RegExp ? pattern : new RegExp(pattern);
  for (const k of [...GET_CACHE.keys()]) if (re.test(k)) GET_CACHE.delete(k);
}

api.interceptors.request.use((config) => {
  config._cacheEpoch = cacheEpoch;
  if ((config.method || 'get').toLowerCase() !== 'get') return config;
  const key = _cacheKey(config);
  if (!_isDedupableGetUrl(key)) return config;

  // Serve from cache if fresh
  const cached = GET_CACHE.get(key);
  const ttl = SHORT_TTL_PATTERNS.some((re) => re.test(key)) ? SHORT_TTL_MS : CACHE_TTL_MS;
  if (cached && Date.now() - cached.ts < ttl) {
    // axios adapter that returns the cached response synchronously
    config.adapter = () => Promise.resolve({
      data: cached.data,
      status: cached.status,
      statusText: 'OK (cached)',
      headers: cached.headers,
      config,
      request: null,
    });
    return config;
  }
  return config;
});

// Wrap api.get so concurrent calls for the same dedupable URL share one promise.
const _rawGet = api.get.bind(api);
api.get = function dedupedGet(url, config) {
  const merged = { ...(config || {}), url, method: 'get', baseURL: api.defaults.baseURL };
  const key = _cacheKey(merged);
  if (!_isDedupableGetUrl(key)) return _rawGet(url, config);
  // Cached → let request interceptor short-circuit
  const cached = GET_CACHE.get(key);
  if (cached && Date.now() - cached.ts < CACHE_TTL_MS) return _rawGet(url, config);
  // In-flight → share the same promise
  const existing = INFLIGHT_GETS.get(key);
  if (existing) return existing;
  const p = _rawGet(url, config).finally(() => INFLIGHT_GETS.delete(key));
  INFLIGHT_GETS.set(key, p);
  return p;
};



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
  (response) => {
    // Populate dedupe cache for successful GETs (skip cached responses)
    try {
      const cfg = response.config || {};
      if ((cfg.method || 'get').toLowerCase() === 'get' && response.statusText !== 'OK (cached)') {
        const key = _cacheKey(cfg);
        if (cfg._cacheEpoch === cacheEpoch && _isDedupableGetUrl(key) && response.status >= 200 && response.status < 300) {
          GET_CACHE.set(key, {
            ts: Date.now(),
            data: response.data,
            status: response.status,
            headers: response.headers,
          });
        }
        INFLIGHT_GETS.delete(key);
      }
    } catch (e) { /* noop */ }
    return response;
  },
  async (error) => {
    // Clear in-flight on error
    try {
      const cfg = error?.config || {};
      if ((cfg.method || 'get').toLowerCase() === 'get') {
        INFLIGHT_GETS.delete(_cacheKey(cfg));
      }
    } catch (e) { /* noop */ }
    const originalRequest = error.config;
    if (!originalRequest) return Promise.reject(error);

    // Never try to refresh the refresh endpoint itself
    const isRefreshCall = originalRequest.url && originalRequest.url.includes('/auth/refresh');
    if (originalRequest._cacheEpoch !== cacheEpoch) return Promise.reject(error);
    if (error.response?.status === 401 && !originalRequest._retry && !isRefreshCall) {
      originalRequest._retry = true;
      try {
        await refreshOnce();
        if (originalRequest._cacheEpoch !== cacheEpoch) return Promise.reject(error);
        return api(originalRequest);
      } catch (e) {
        // Refresh failed — broadcast so AuthContext can clear user state
        if (originalRequest._cacheEpoch === cacheEpoch && typeof window !== 'undefined') {
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
