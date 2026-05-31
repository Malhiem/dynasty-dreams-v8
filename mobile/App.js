import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { AuthProvider, useAuth } from './src/contexts/AuthContext';
import AppNavigator, { navigateFromPush } from './src/navigation/AppNavigator';
import { usePushRegistration } from './src/hooks/usePushRegistration';

function PushBridge({ children }) {
  const { user } = useAuth();
  // Register once user is logged in. When user logs out, userId goes null
  // and the effect cleans up listeners; tokens persist on server (marked
  // inactive via explicit logout flow if needed).
  // `navigateFromPush` deep-links based on the notification's `data` payload —
  // currently routes crown events (championship/consolation) to the Trophy
  // Case in Profile. See navigation/AppNavigator.js → navigateFromPush.
  usePushRegistration(user?.id || null, navigateFromPush);
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <StatusBar style="light" />
      <PushBridge>
        <AppNavigator />
      </PushBridge>
    </AuthProvider>
  );
}
