// Expo app config. app.json holds the static settings; the EAS project id is
// supplied per environment (run `eas init`, then set EXPO_PUBLIC_EAS_PROJECT_ID)
// so a placeholder id is never shipped. Without it the app runs normally and
// push registration is skipped (see src/hooks/usePushRegistration.js).
module.exports = ({ config }) => ({
  ...config,
  extra: {
    ...(config.extra || {}),
    eas: { projectId: process.env.EXPO_PUBLIC_EAS_PROJECT_ID || undefined },
  },
});
