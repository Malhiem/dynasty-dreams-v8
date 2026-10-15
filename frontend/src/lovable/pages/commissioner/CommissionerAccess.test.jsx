import React, { act, useState } from 'react';
import { createRoot } from 'react-dom/client';
import CommissionerAccess from './CommissionerAccess';
import { useActiveLeague } from '@/hooks/use-active-league';
import { useAuth } from '@/contexts/AuthContext';
import api from '@/lib/api';

jest.mock('@/components/layout/AppLayout', () => ({ AppLayout: ({ children }) => children }), { virtual: true });
jest.mock('@/hooks/use-active-league', () => ({ useActiveLeague: jest.fn() }), { virtual: true });
jest.mock('@/contexts/AuthContext', () => ({ useAuth: jest.fn() }), { virtual: true });
jest.mock('@/lib/api', () => ({ __esModule: true, default: { get: jest.fn() } }), { virtual: true });

let container, root;
const league = (commissioner = 'U') => ({ id: 'L', commissioner_id: commissioner, co_commissioners: [], admin_ids: [] });
function Editor() {
  const [draft, setDraft] = useState(0);
  return <button onClick={() => setDraft(value => value + 1)}>Draft {draft}</button>;
}
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'U' }, loading: false });
  useActiveLeague.mockReturnValue({ leagueId: 'L', league: league(), loading: false });
  api.get.mockResolvedValue({ data: league() });
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

test('refreshing identical permissions retains editor state; changed permissions revoke access', async () => {
  await act(async () => root.render(<CommissionerAccess component={Editor} />));
  await act(async () => container.querySelector('button').click());
  expect(container.textContent).toBe('Draft 1');
  // A league refresh returns newly allocated permission arrays with the same values.
  useActiveLeague.mockReturnValue({ leagueId: 'L', league: league(), loading: false });
  await act(async () => root.render(<CommissionerAccess component={Editor} />));
  expect(container.textContent).toBe('Draft 1');
  expect(api.get).toHaveBeenCalledTimes(1);
  useActiveLeague.mockReturnValue({ leagueId: 'L', league: league('Other'), loading: false });
  api.get.mockResolvedValue({ data: league('Other') });
  await act(async () => root.render(<CommissionerAccess component={Editor} />));
  expect(container.querySelector('button')).toBeNull();
  expect(container.textContent).toContain('Only league administrators');
  expect(api.get).toHaveBeenCalledTimes(2);
});

test('failed authorization lookup never mounts administrative editors', async () => {
  api.get.mockRejectedValue(new Error('network failed'));
  await act(async () => root.render(<CommissionerAccess component={Editor} />));
  expect(container.querySelector('button')).toBeNull();
  expect(container.textContent).toContain('Only league administrators');
});
