const mockSocket = { removeAllListeners: jest.fn(), disconnect: jest.fn(), on: jest.fn(), off: jest.fn() };
const mockIo = jest.fn(() => mockSocket);
jest.mock('socket.io-client', () => ({ io: (...a) => mockIo(...a) }));
const mockFresh = jest.fn();
jest.mock('../src/lib/api', () => ({ BACKEND_URL: 'http://backend', getFreshAccessToken: (...a) => mockFresh(...a) }));
const { getSocket, resetSocket, socketAuth } = require('../src/lib/socket');

beforeEach(() => { jest.clearAllMocks(); resetSocket(); });

test('the socket is created with an auth callback (the server refuses token-less handshakes)', () => {
  getSocket();
  const opts = mockIo.mock.calls[0][1];
  expect(opts.path).toBe('/api/socket.io');
  expect(opts.autoConnect).toBe(false);
  expect(opts.auth).toBe(socketAuth);
});

test('the auth callback supplies the current access token', async () => {
  mockFresh.mockResolvedValue('tok-123');
  const cb = jest.fn();
  socketAuth(cb);
  await new Promise((r) => setImmediate(r));
  expect(cb).toHaveBeenCalledWith({ token: 'tok-123' });
});

test('the auth callback degrades to an empty token (not a hang) when no token can be obtained', async () => {
  mockFresh.mockRejectedValue(new Error('x'));
  const cb = jest.fn();
  socketAuth(cb);
  await new Promise((r) => setImmediate(r));
  expect(cb).toHaveBeenCalledWith({ token: '' });
});

test('the socket is a singleton until reset; reset disconnects so the next user gets a fresh handshake', () => {
  const a = getSocket(); const b = getSocket();
  expect(a).toBe(b); expect(mockIo).toHaveBeenCalledTimes(1);
  resetSocket();
  expect(mockSocket.disconnect).toHaveBeenCalled();
  getSocket();
  expect(mockIo).toHaveBeenCalledTimes(2);
});
