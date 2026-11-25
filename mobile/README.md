# Dynasty Dreams Mobile App

## Setup

```bash
cd mobile
npm install  # or yarn
npx expo start
```

## Architecture
- **Framework**: React Native with Expo SDK 52
- **Navigation**: React Navigation (Bottom Tabs + Native Stack)
- **State**: React Context + component state
- **Styling**: React Native StyleSheet
- **API**: Axios with token refresh interceptor
- **Real-time**: Socket.IO client
- **Secure Storage**: expo-secure-store for JWT tokens
- **Push Notifications**: expo-notifications

## Screens (15)
| Screen | Description | API Endpoints |
|--------|-------------|---------------|
| Login | Email/password auth | POST /auth/login |
| Register | Account creation | POST /auth/register |
| Dashboard | Stats overview, quick actions | GET /leagues, /notifications/count |
| Leagues | Browse/create leagues | GET/POST /leagues |
| Players | Search/filter NHL players | GET /players |
| PlayerDetail | Full stat breakdown | GET /players/{id} |
| DraftRoom | Snake draft with live picks | GET/POST /drafts/{id}/* |
| AuctionDraft | Auction bidding interface | GET/POST /drafts/{id}/auction/* |
| TradeBlock | Players available for trade | GET/POST /trade-block |
| Waivers | FAAB bidding system | GET/POST /waivers/* |
| Roster | Team roster management | GET/POST /roster/{id}/* |
| Standings | League standings + matchups | GET /leagues/{id}/standings, /matchups/* |
| SalaryCap | Contracts + cap tracking | GET/POST /contracts, /salary-cap/* |
| ActivityFeed | Real-time league timeline | GET /activity/{id}, WebSocket |
| Notifications | Push notification center | GET /notifications |

## Navigation Structure
```
MainTabs
├── Home Tab (Stack)
│   ├── Dashboard
│   ├── LeagueDetail
│   ├── Standings
│   └── Notifications
├── Players Tab (Stack)
│   ├── PlayersList
│   ├── PlayerDetail
│   ├── DraftRoom
│   └── AuctionDraft
├── League Tab (Stack)
│   ├── Roster
│   ├── TradeBlock
│   ├── Waivers
│   └── SalaryCap
└── Feed Tab (Stack)
    ├── ActivityFeed
    └── Standings
```

## WebSocket Events (shared with web)
- `draft_pick`, `draft_chat`, `auction_bid`, `auction_resolved`
- `trade_proposed`, `trade_accepted`, `waivers_processed`
- `week_simulated`, `activity_feed`, `notification`

## Design System
- Background: #0A0A0A
- Surface: #141414
- Brand: #00D2FF
- Accent: #FF3B30
- Success: #34C759
- Warning: #FF9F0A
- Text Primary: #FFFFFF
- Text Secondary: #A1A1AA

## Next Steps
1. Update `API_BASE_URL` in `src/lib/api.js` to your production URL
2. Implement each screen's API calls (marked with TODO)
3. Add push notification token registration
4. Configure app.json for iOS/Android builds
5. Set up EAS Build for distribution

## Notes (build and config)
- Entry point is `App.js` through `expo/AppEntry` and React Navigation. There is no expo-router.
- `assets/` holds placeholder icon, splash and favicon images. Replace them with real artwork before store submission.
- Push notifications need an EAS project id: run `eas init`, then set `EXPO_PUBLIC_EAS_PROJECT_ID` (see `app.config.js`). Without it push registration is skipped.
- `npm test` runs the Jest suite; `npm run bundle-check` makes a real Android Metro bundle.
