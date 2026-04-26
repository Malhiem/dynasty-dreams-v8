import React from 'react';
import { View, Text, Image, StyleSheet } from 'react-native';

/**
 * TeamLogo — mobile mirror of the web TeamLogo.
 * Accepts an optional data-URL or http(s) image; falls back to a circular
 * gradient with the team initials.
 */
export default function TeamLogo({ logo, name, abbr, size = 'md', style }) {
  const dim = sizes[size] || sizes.md;
  const initials = (abbr || (name || '').slice(0, 2)).toUpperCase();
  const showImage = !!logo;

  return (
    <View
      style={[
        styles.wrap,
        { width: dim.box, height: dim.box, borderRadius: dim.box / 2 },
        style,
      ]}
    >
      {showImage ? (
        <Image
          source={{ uri: logo }}
          style={{ width: dim.box, height: dim.box, borderRadius: dim.box / 2 }}
          resizeMode="cover"
        />
      ) : (
        <Text style={[styles.text, { fontSize: dim.font }]}>{initials}</Text>
      )}
    </View>
  );
}

const sizes = {
  xs: { box: 20, font: 9 },
  sm: { box: 28, font: 11 },
  md: { box: 40, font: 14 },
  lg: { box: 64, font: 22 },
  xl: { box: 96, font: 32 },
};

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: '#1A1A1A',
    borderWidth: 1.5,
    borderColor: '#00D2FF55',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  text: {
    color: '#00D2FF',
    fontWeight: '800',
    letterSpacing: 0.5,
  },
});
