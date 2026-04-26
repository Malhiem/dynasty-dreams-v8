import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Alert, StyleSheet } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import api from '../lib/api';
import TeamLogo from './TeamLogo';

const MAX_BYTES = 1 * 1024 * 1024; // 1 MB
const ACCEPTED_MIME = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif'];

/**
 * TeamLogoUploader (mobile) — taps to launch the image library, validates
 * size + type, and POSTs to /api/teams/{id}/logo. Calls onChange(url|null)
 * after a successful upload or removal.
 */
export default function TeamLogoUploader({ teamId, name, abbr, logo, size = 'lg', onChange }) {
  const [busy, setBusy] = useState(false);

  const pickAndUpload = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert('Permission required', 'Please allow photo library access to upload a team logo.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.9,
      allowsEditing: true,
      aspect: [1, 1],
    });
    if (result.canceled || !result.assets?.length) return;
    const asset = result.assets[0];

    // Client-side validation: size
    if (asset.fileSize && asset.fileSize > MAX_BYTES) {
      Alert.alert('Image too large', `Max 1 MB. Selected: ${(asset.fileSize / 1024 / 1024).toFixed(2)} MB.`);
      return;
    }
    // Client-side validation: mime guess
    const mime = asset.mimeType || guessMime(asset.uri);
    if (mime && !ACCEPTED_MIME.includes(mime)) {
      Alert.alert('Unsupported image', 'Use PNG, JPEG, WEBP, or GIF.');
      return;
    }

    setBusy(true);
    try {
      const form = new FormData();
      form.append('file', {
        uri: asset.uri,
        name: asset.fileName || `logo.${(mime || 'image/png').split('/')[1]}`,
        type: mime || 'image/png',
      });
      const { data } = await api.post(`/teams/${teamId}/logo`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      onChange?.(data?.logo_url || null);
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Failed to upload logo';
      Alert.alert('Upload failed', detail);
    } finally {
      setBusy(false);
    }
  };

  const removeLogo = async () => {
    Alert.alert('Remove logo?', 'Your team will revert to using initials.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: async () => {
          setBusy(true);
          try {
            await api.delete(`/teams/${teamId}/logo`);
            onChange?.(null);
          } catch (err) {
            Alert.alert('Failed', err?.response?.data?.detail || 'Could not remove logo');
          } finally {
            setBusy(false);
          }
        },
      },
    ]);
  };

  return (
    <View style={styles.wrap}>
      <TouchableOpacity
        onPress={pickAndUpload}
        onLongPress={logo ? removeLogo : undefined}
        disabled={busy}
        accessibilityRole="button"
        accessibilityLabel={logo ? 'Change team logo. Long-press to remove.' : 'Upload team logo'}
        testID="team-logo-upload-btn"
      >
        <TeamLogo logo={logo} name={name} abbr={abbr} size={size} />
        {busy && (
          <View style={styles.overlay}>
            <ActivityIndicator color="#00D2FF" />
          </View>
        )}
      </TouchableOpacity>
      {!busy && (
        <Text style={styles.hint}>{logo ? 'Tap to change · Long-press to remove' : 'Tap to upload'}</Text>
      )}
    </View>
  );
}

const guessMime = (uri = '') => {
  const ext = uri.split('.').pop()?.toLowerCase();
  return (
    {
      png: 'image/png',
      jpg: 'image/jpeg',
      jpeg: 'image/jpeg',
      webp: 'image/webp',
      gif: 'image/gif',
    }[ext] || null
  );
};

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', gap: 4 },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.6)',
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  hint: { color: '#71717A', fontSize: 10, marginTop: 2 },
});
