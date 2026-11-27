import { Alert } from 'react-native';

// Human-readable message from an axios/FastAPI error: `detail` may be a string,
// a validation-error list, or an object with a `message`.
export function errorMessage(e, fallback = 'Something went wrong. Please try again.') {
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0];
    return typeof first === 'string' ? first : (first?.msg || fallback);
  }
  if (detail && typeof detail === 'object' && typeof detail.message === 'string') return detail.message;
  if (e?.response?.status) return `${fallback} (error ${e.response.status})`;
  if (e?.code === 'ECONNABORTED') return 'The request timed out. Check your connection and try again.';
  if (e?.message === 'Network Error') return 'Cannot reach the server. Check your connection and try again.';
  return fallback;
}

// Tell the user an action they started failed (instead of only logging it).
export function showActionError(e, title = 'Action failed') {
  console.warn(`[${title}]`, e?.response?.data || e?.message || e);
  Alert.alert(title, errorMessage(e));
}

// Load-failure helper: log it, and return a message the screen can show with a
// Retry button, so a failed load never looks like an empty one.
export function loadFailure(e, what = 'data') {
  console.warn(`[load ${what}]`, e?.response?.data || e?.message || e);
  return errorMessage(e, `Could not load ${what}.`);
}
