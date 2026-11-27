jest.mock('react-native', () => ({ Alert: { alert: jest.fn() } }));
const { Alert } = require('react-native');
const { errorMessage, showActionError } = require('../src/lib/errors');

describe('errorMessage', () => {
  test('uses a string detail from the API', () => {
    expect(errorMessage({ response: { status: 409, data: { detail: 'Pick already advanced' } } })).toBe('Pick already advanced');
  });
  test('uses the first validation message from a list', () => {
    expect(errorMessage({ response: { status: 422, data: { detail: [{ msg: 'field required' }] } } })).toBe('field required');
  });
  test('falls back with the status code', () => {
    expect(errorMessage({ response: { status: 500, data: {} } })).toMatch(/error 500/);
  });
  test('explains network failures', () => {
    expect(errorMessage({ message: 'Network Error' })).toMatch(/Cannot reach the server/);
  });
});

test('showActionError alerts the user with the server message', () => {
  jest.spyOn(console, 'warn').mockImplementation(() => {});
  showActionError({ response: { status: 403, data: { detail: 'Not your turn' } } }, 'Could not make that pick');
  expect(Alert.alert).toHaveBeenCalledWith('Could not make that pick', 'Not your turn');
});
