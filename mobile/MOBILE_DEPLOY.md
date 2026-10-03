# Dynasty Dreams — Mobile Deploy Guide

This guide covers configuring the React Native (Expo) app for **real-device push notifications** and shipping to the App Store / Play Store.

## ⚠️ Required: One-time EAS Setup

The placeholder `projectId` in `app.json` (`00000000-0000-0000-0000-000000000000`) MUST be replaced with a real EAS project ID before you can deliver push notifications to physical devices.

### Step 1 — Install EAS CLI globally

```bash
npm install -g eas-cli
```

### Step 2 — Log in to your Expo account

```bash
eas login
```

If you don't have an Expo account yet, create one free at https://expo.dev/signup.

### Step 3 — Initialize EAS in the mobile workspace

```bash
cd /app/mobile
eas init
```

This command:
- Creates an Expo project (or links an existing one)
- Auto-fills `expo.extra.eas.projectId` in `app.json` with the real UUID
- Generates `eas.json` if not present

### Step 4 — Verify

```bash
cat app.json | grep projectId
# Expected: "projectId": "your-real-uuid-here" (NOT 00000000…)
```

### Step 5 — Test push delivery

Open the app on a real device, log in, then from the backend:

```bash
curl -X POST $REACT_APP_BACKEND_URL/api/push/test -H "Authorization: Bearer $TOKEN"
```

You should see "Dynasty Dreams · Push notifications are working! 🏒" within seconds.

---

## Build & Submit

```bash
# Production iOS build (App Store)
eas build --platform ios --profile production

# Production Android build (Play Store)
eas build --platform android --profile production

# Submit (after build completes)
eas submit -p ios   # uploads .ipa → App Store Connect
eas submit -p android   # uploads .aab → Google Play Console
```

---

## Push notification troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `[push] No Expo projectId found; skipping push registration` in logs | `app.json` still has placeholder UUID | Re-run `eas init` |
| Token registers but no push arrives on device | Notification permissions denied | Settings → Dynasty Dreams → Notifications → Allow |
| `DeviceNotRegistered` errors in backend logs | Tester uninstalled and reinstalled the app | Backend auto-deactivates token; re-login refreshes it |
| Pushes work in dev but not in TestFlight | iOS APNs entitlement missing | `eas credentials -p ios` → "Push Key" → "Set up a new key" |

## Token lifecycle notes

- The backend stores Expo push tokens in `db.push_tokens` with `is_active: bool`.
- On user logout (mobile), the app does NOT auto-deactivate (token persists across sessions on same device).
- Receipts auto-deactivate `DeviceNotRegistered` tokens within `send_push()`.
- Re-registering the same token is idempotent (Mongo upsert).
