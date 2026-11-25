// Real handshake against a running backend. Skipped unless MOBILE_TEST_BACKEND_URL is set, e.g.
//   EXPO_PUBLIC_BACKEND_URL=http://127.0.0.1:8001 MOBILE_TEST_BACKEND_URL=http://127.0.0.1:8001 \
//   MOBILE_TEST_EMAIL=... MOBILE_TEST_PASSWORD=... npx jest --no-cache
// (babel-preset-expo inlines EXPO_PUBLIC_* at transform time, so it must be set when jest starts.)
const URL_ = process.env.MOBILE_TEST_BACKEND_URL;
const run = URL_ ? describe : describe.skip;

run('socket handshake against the real backend', () => {
  const store = {};
  let api; let socketLib; let io;
  beforeAll(async () => {
    jest.resetModules();
    jest.doMock('expo-secure-store', () => ({
      setItemAsync: async (k, v) => { store[k] = v; },
      getItemAsync: async (k) => (k in store ? store[k] : null),
      deleteItemAsync: async (k) => { delete store[k]; },
    }));
    api = require('../src/lib/api'); socketLib = require('../src/lib/socket'); io = require('socket.io-client').io;
    const { data } = await api.default.post('/auth/login', { email: process.env.MOBILE_TEST_EMAIL, password: process.env.MOBILE_TEST_PASSWORD });
    await api.setTokens(data.access_token, data.refresh_token);
  });
  afterAll(() => socketLib.resetSocket());

  function connect(socket) {
    return new Promise((resolve) => {
      socket.once('connect', () => resolve('connected'));
      socket.once('connect_error', (e) => resolve(`refused: ${e.message}`));
      socket.connect();
    });
  }

  test('the app socket (token supplied by lib/socket) connects', async () => {
    expect(await connect(socketLib.getSocket())).toBe('connected');
    socketLib.resetSocket();
  }, 20000);

  test('a handshake without a token is refused (the old behaviour)', async () => {
    const bare = io(URL_, { path: '/api/socket.io', transports: ['websocket'], autoConnect: false });
    expect(await connect(bare)).toMatch(/^refused/);
    bare.close();
  }, 20000);
});
