process.env.EXPO_PUBLIC_BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || 'http://test.invalid';
const store = {};
jest.mock('expo-secure-store', () => ({
  setItemAsync: jest.fn(async (k, v) => { store[k] = v; }),
  getItemAsync: jest.fn(async (k) => (k in store ? store[k] : null)),
  deleteItemAsync: jest.fn(async (k) => { delete store[k]; }),
}));
const handlers = {};
jest.mock('axios', () => {
  const instance = jest.fn(async (cfg) => ({ data: { retried: cfg.url } }));
  instance.interceptors = {
    request: { use: (fn) => { handlers.request = fn; } },
    response: { use: (ok, err) => { handlers.responseError = err; } },
  };
  return { create: () => instance, post: jest.fn(), __instance: instance };
});
const axios = require('axios');
const api = require('../src/lib/api');

function jwt(expOffsetSeconds) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64').replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  return `${b64({ alg: 'HS256' })}.${b64({ exp: Math.floor(Date.now() / 1000) + expOffsetSeconds })}.sig`;
}
beforeEach(async () => { Object.keys(store).forEach((k) => delete store[k]); axios.post.mockReset(); api.setAuthLostHandler(null); await api.clearTokens(); });

describe('secondsUntilExpiry', () => {
  test('reads exp from a JWT', () => { expect(api.secondsUntilExpiry(jwt(120))).toBeGreaterThan(100); });
  test('negative once expired', () => { expect(api.secondsUntilExpiry(jwt(-5))).toBeLessThan(0); });
  test('null for garbage', () => { expect(api.secondsUntilExpiry('nope')).toBeNull(); });
});

describe('getFreshAccessToken', () => {
  test('returns the stored token while it is valid', async () => {
    const t = jwt(600); await api.setTokens(t, 'refresh');
    expect(await api.getFreshAccessToken()).toBe(t);
    expect(axios.post).not.toHaveBeenCalled();
  });
  test('refreshes an expired token before use', async () => {
    await api.setTokens(jwt(-10), 'r1');
    const fresh = jwt(900);
    axios.post.mockResolvedValue({ data: { access_token: fresh, refresh_token: 'r2' } });
    expect(await api.getFreshAccessToken()).toBe(fresh);
    expect(store.refresh_token).toBe('r2');
  });
  test('null when expired and the refresh fails', async () => {
    await api.setTokens(jwt(-10), 'r1');
    axios.post.mockRejectedValue(new Error('401'));
    expect(await api.getFreshAccessToken()).toBeNull();
  });
});

describe('401 handling', () => {
  test('refreshes once and retries the request', async () => {
    await api.setTokens(jwt(-10), 'r1');
    axios.post.mockResolvedValue({ data: { access_token: jwt(900), refresh_token: 'r2' } });
    const res = await handlers.responseError({ response: { status: 401 }, config: { url: '/leagues' } });
    expect(res.data.retried).toBe('/leagues');
  });
  test('signs the user out when the session cannot be refreshed', async () => {
    const lost = jest.fn(); api.setAuthLostHandler(lost);
    await api.setTokens(jwt(-10), 'r1');
    axios.post.mockRejectedValue(new Error('refresh expired'));
    await expect(handlers.responseError({ response: { status: 401 }, config: { url: '/leagues' } })).rejects.toBeTruthy();
    expect(lost).toHaveBeenCalledTimes(1);
    expect(store.access_token).toBeUndefined();
  });
  test('signs out when there is no refresh token at all', async () => {
    const lost = jest.fn(); api.setAuthLostHandler(lost);
    await expect(handlers.responseError({ response: { status: 401 }, config: { url: '/x' } })).rejects.toBeTruthy();
    expect(lost).toHaveBeenCalledTimes(1);
  });
  test('concurrent 401s share one refresh call', async () => {
    await api.setTokens(jwt(-10), 'r1');
    axios.post.mockResolvedValue({ data: { access_token: jwt(900), refresh_token: 'r2' } });
    await Promise.all([1, 2, 3].map((n) => handlers.responseError({ response: { status: 401 }, config: { url: `/a${n}` } })));
    expect(axios.post).toHaveBeenCalledTimes(1);
  });
});
