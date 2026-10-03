// Register for Expo Push Notifications and sync token with backend.
// Follows the Expo integration playbook (exp.host/--/api/v2/push/send).
import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';
import api from '../lib/api';

// Foreground behaviour: show banner, play sound, update badge.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: true,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

async function _registerForPushToken() {
  if (Platform.OS === 'android') {
    try {
      await Notifications.setNotificationChannelAsync('default', {
        name: 'Dynasty Dreams',
        importance: Notifications.AndroidImportance.MAX,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: '#06B6D4',
      });
    } catch (e) {
      // channel creation is best-effort
    }
  }

  if (!Device.isDevice) {
    // Simulators / emulators don't support push. Skip quietly.
    return null;
  }

  const existing = await Notifications.getPermissionsAsync();
  let finalStatus = existing.status;
  if (existing.status !== 'granted') {
    const asked = await Notifications.requestPermissionsAsync();
    finalStatus = asked.status;
  }
  if (finalStatus !== 'granted') return null;

  const projectId =
    Constants?.expoConfig?.extra?.eas?.projectId
    || Constants?.easConfig?.projectId;
  if (!projectId) {
    console.warn('[push] No Expo projectId found; skipping push registration');
    return null;
  }

  try {
    const res = await Notifications.getExpoPushTokenAsync({ projectId });
    return res?.data || null;
  } catch (e) {
    console.warn('[push] getExpoPushTokenAsync failed', e?.message);
    return null;
  }
}

/**
 * usePushRegistration — call from the root App once user is authenticated.
 * - Requests permissions + Expo push token.
 * - POSTs token to /api/push/register-token.
 * - Installs foreground + response listeners.
 * @param {string|null} userId - authenticated user id (null if not logged in)
 * @param {Function} [onResponse] - called when user taps a notification
 */
export function usePushRegistration(userId, onResponse) {
  const receivedRef = useRef(null);
  const responseRef = useRef(null);

  useEffect(() => {
    if (!userId) return undefined;
    let cancelled = false;

    (async () => {
      const token = await _registerForPushToken();
      if (cancelled || !token) return;
      try {
        await api.post('/push/register-token', {
          expo_push_token: token,
          platform: Platform.OS,
          device_name: Device.deviceName || undefined,
        });
      } catch (e) {
        console.warn('[push] register-token failed', e?.response?.data || e?.message);
      }
    })();

    // Foreground notification listener (already handled by setNotificationHandler,
    // but useful if we want to update badges / counters in-app)
    receivedRef.current = Notifications.addNotificationReceivedListener(() => {
      // No-op hook; UI reloading is driven by the data payload → screens refresh on focus.
    });
    // User tapped a notification → caller can navigate
    responseRef.current = Notifications.addNotificationResponseReceivedListener((resp) => {
      try {
        onResponse && onResponse(resp?.notification?.request?.content?.data || {});
      } catch (e) {
        // ignore
      }
    });

    return () => {
      cancelled = true;
      try { receivedRef.current && Notifications.removeNotificationSubscription(receivedRef.current); } catch (e) {}
      try { responseRef.current && Notifications.removeNotificationSubscription(responseRef.current); } catch (e) {}
    };
  }, [userId, onResponse]);
}
