import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { AuthProvider, useAuth } from './src/contexts/AuthContext';
import AppNavigator from './src/navigation/AppNavigator';
import { usePushRegistration } from './src/hooks/usePushRegistration';

function PushBridge({ children }) {
  const { user } = useAuth();
  // Register once user is logged in. When user logs out, userId goes null and
  // the effect cleans up listeners; tokens persist on server (marked inactive
  // via explicit logout flow if needed).
  usePushRegistration(user?.id || null);
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
