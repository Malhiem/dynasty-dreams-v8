import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, SafeAreaView, KeyboardAvoidingView, Platform } from 'react-native';
import { useAuth } from '../contexts/AuthContext';

export default function RegisterScreen({ navigation }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();

  const handleRegister = async () => {
    setError(''); setLoading(true);
    try { await register(email, password, name); }
    catch (e) { setError(e.response?.data?.detail || 'Registration failed'); }
    setLoading(false);
  };

  return (
    <SafeAreaView style={s.container}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={s.inner}>
        <Text style={s.title}>CREATE{'\n'}ACCOUNT</Text>
        <Text style={s.subtitle}>Start your dynasty journey</Text>
        {error ? <Text style={s.error}>{error}</Text> : null}
        <TextInput style={s.input} placeholder="Full Name" placeholderTextColor="#52525B" value={name} onChangeText={setName} />
        <TextInput style={s.input} placeholder="Email" placeholderTextColor="#52525B" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
        <TextInput style={s.input} placeholder="Password" placeholderTextColor="#52525B" value={password} onChangeText={setPassword} secureTextEntry />
        <TouchableOpacity style={s.button} onPress={handleRegister} disabled={loading}>
          <Text style={s.buttonText}>{loading ? 'Creating...' : 'Create Account'}</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => navigation.navigate('Login')}>
          <Text style={s.link}>Already have an account? <Text style={s.accent}>Sign in</Text></Text>
        </TouchableOpacity>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0A' },
  inner: { flex: 1, justifyContent: 'center', padding: 24 },
  title: { fontSize: 44, fontWeight: '900', color: '#00D2FF', textAlign: 'center', marginBottom: 8 },
  subtitle: { fontSize: 16, color: '#A1A1AA', textAlign: 'center', marginBottom: 32 },
  error: { color: '#FF3B30', textAlign: 'center', marginBottom: 16 },
  input: { backgroundColor: '#141414', borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: 16, color: '#fff', fontSize: 16, marginBottom: 12 },
  button: { backgroundColor: '#00D2FF', borderRadius: 8, padding: 16, alignItems: 'center', marginTop: 8, marginBottom: 24 },
  buttonText: { color: '#000', fontSize: 16, fontWeight: '700' },
  link: { color: '#A1A1AA', textAlign: 'center' },
  accent: { color: '#00D2FF' },
});
