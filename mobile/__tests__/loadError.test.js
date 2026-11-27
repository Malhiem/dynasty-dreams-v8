const fs = require('fs');
const path = require('path');

jest.mock('react-native', () => ({
  Alert: { alert: jest.fn() },
  View: 'View', Text: 'Text', TouchableOpacity: 'TouchableOpacity',
  StyleSheet: { create: (s) => s },
}));
const { loadFailure } = require('../src/lib/errors');
const LoadError = require('../src/components/LoadError').default;

describe('loadFailure', () => {
  beforeEach(() => jest.spyOn(console, 'warn').mockImplementation(() => {}));

  test('returns a message naming what failed, with the server detail when present', () => {
    expect(loadFailure({ response: { status: 403, data: { detail: 'Not a league member' } } }, 'the roster'))
      .toBe('Not a league member');
  });
  test('explains offline failures', () => {
    expect(loadFailure({ message: 'Network Error' }, 'standings')).toMatch(/Cannot reach the server/);
  });
  test('falls back to a "could not load X" message', () => {
    expect(loadFailure({}, 'the roster')).toBe('Could not load the roster.');
  });
  test('still logs for debugging', () => {
    loadFailure({ message: 'boom' }, 'x');
    expect(console.warn).toHaveBeenCalled();
  });
});

describe('LoadError', () => {
  test('renders nothing without a message', () => {
    expect(LoadError({ message: null })).toBeNull();
  });
  test('shows the message and a Retry button that calls onRetry', () => {
    const onRetry = jest.fn();
    const el = LoadError({ message: 'Could not load the roster.', onRetry });
    const flat = JSON.stringify(el, (k, v) => (typeof v === 'function' ? '[fn]' : v));
    expect(flat).toContain('Could not load the roster.');
    expect(flat).toContain('Retry');
    // find the TouchableOpacity and press it
    const find = (n) => {
      if (!n || typeof n !== 'object') return null;
      if (n.type === 'TouchableOpacity') return n;
      const kids = [].concat(n.props?.children || []);
      for (const k of kids) { const r = find(k); if (r) return r; }
      return null;
    };
    find(el).props.onPress();
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

// Regression guard: load failures must reach the user, not just the console.
describe('screens do not swallow load errors', () => {
  const dir = path.join(__dirname, '..', 'src', 'screens');
  const files = fs.readdirSync(dir).filter((f) => f.endsWith('.js'));
  test.each(files)('%s', (f) => {
    const src = fs.readFileSync(path.join(dir, f), 'utf8');
    expect(src).not.toMatch(/catch \(e\) \{ console\.error\(e\); \}/);
    expect(src).not.toMatch(/catch \(e\) \{\}/);
    expect(src).not.toMatch(/\.catch\(console\.error\)/);
    expect(src).not.toMatch(/\.catch\(\(\) => \{\}\)/);
  });

  const loaders = ['Dashboard', 'Leagues', 'Roster', 'Waivers', 'Players', 'Notifications', 'TradeBlock',
    'Standings', 'ActivityFeed', 'Matchup', 'SalaryCap', 'DraftRoom', 'AuctionDraft', 'PlayerDetail'];
  test.each(loaders)('%sScreen shows LoadError with a retry', (n) => {
    const src = fs.readFileSync(path.join(dir, `${n}Screen.js`), 'utf8');
    expect(src).toMatch(/<LoadError message=\{loadError\} onRetry=/);
    expect(src).toMatch(/loadFailure\(/);
  });
});
