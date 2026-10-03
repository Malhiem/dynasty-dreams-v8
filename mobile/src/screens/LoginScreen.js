import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, SafeAreaView, KeyboardAvoidingView, Platform } from 'react-native';
import { useAuth } from '../contexts/AuthContext';

export default function LoginScreen({ navigation }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();

  const handleLogin = async () => {
    setError(''); setLoading(true);
    try {
      await login(email, password);
    } catch (e) {
      setError(e.response?.data?.detail || 'Login failed');
    }
    setLoading(false);
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.inner}>
        <Text style={styles.logo}>DYNASTY{'\n'}DREAMS</Text>
        <Text style={styles.subtitle}>Sign in to your account</Text>
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <TextInput style={styles.input} placeholder="Email" placeholderTextColor="#52525B" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
        <TextInput style={styles.input} placeholder="Password" placeholderTextColor="#52525B" value={password} onChangeText={setPassword} secureTextEntry />
        <TouchableOpacity style={styles.button} onPress={handleLogin} disabled={loading}>
          <Text style={styles.buttonText}>{loading ? 'Signing in...' : 'Sign In'}</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => navigation.navigate('Register')}>
          <Text style={styles.link}>Don't have an account? <Text style={styles.linkAccent}>Create one</Text></Text>
        </TouchableOpacity>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  inner: { flex: 1, justifyContent: 'center', padding: 24 },
  logo: { fontFamily: Platform.OS === 'ios' ? 'System' : 'sans-serif-condensed', fontSize: 48, fontWeight: '900', color: '#00D2FF', textAlign: 'center', marginBottom: 8, letterSpacing: -1 },
  subtitle: { fontSize: 16, color: '#A1A1AA', textAlign: 'center', marginBottom: 32 },
  error: { color: '#FF3B30', textAlign: 'center', marginBottom: 16, fontSize: 14 },
  input: { backgroundColor: '#141414', borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: 16, color: '#fff', fontSize: 16, marginBottom: 12 },
  button: { backgroundColor: '#00D2FF', borderRadius: 8, padding: 16, alignItems: 'center', marginTop: 8, marginBottom: 24 },
  buttonText: { color: '#000', fontSize: 16, fontWeight: '700' },
  link: { color: '#A1A1AA', textAlign: 'center', fontSize: 14 },
  linkAccent: { color: '#00D2FF' },
});
