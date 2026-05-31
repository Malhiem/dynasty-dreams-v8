import React from 'react';
import { NavigationContainer, createNavigationContainerRef } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useAuth } from '../contexts/AuthContext';

// Navigation ref — lets non-component callers (e.g. push notification
// response handlers in App.js) navigate without prop-drilling through the
// tree. See `navigateFromPush` below for the typed entrypoint we expose
// for the crown-event deep-link.
export const navigationRef = createNavigationContainerRef();

/**
 * Deep-link router for push notification taps. Reads `data.type` and routes
 * accordingly. Safe to call before mount — silently no-ops if the navigator
 * isn't ready yet.
 *
 * Supported types:
 *   • "crown"   → Profile screen (Trophy Case section)
 *   • default   → Notifications screen so the user sees the full list
 */
export function navigateFromPush(data) {
  if (!navigationRef.isReady() || !data || typeof data !== 'object') return;
  try {
    if (data.type === 'crown') {
      // Profile is inside the Home tab → navigate via nested route. We
      // pass the league_id so the screen could (future enhancement) deep-
      // scroll to the trophy that was just awarded.
      navigationRef.navigate('Home', {
        screen: 'Profile',
        params: {
          highlightLeagueId: data.league_id,
          highlightTeamId: data.team_id,
          highlightEvent: data.event,        // "championship" | "consolation"
          season: data.season,
          isWinner: !!data.is_winner,
        },
      });
      return;
    }
    // Fallback for any other typed notification — show the full list
    navigationRef.navigate('Home', { screen: 'Notifications' });
  } catch (e) {
    // Don't crash the app on a malformed payload
    // eslint-disable-next-line no-console
    console.warn('[push-nav] failed', e?.message || e);
  }
}

// Screens
import LoginScreen from '../screens/LoginScreen';
import RegisterScreen from '../screens/RegisterScreen';
import DashboardScreen from '../screens/DashboardScreen';
import LeaguesScreen from '../screens/LeaguesScreen';
import PlayersScreen from '../screens/PlayersScreen';
import PlayerDetailScreen from '../screens/PlayerDetailScreen';
import DraftRoomScreen from '../screens/DraftRoomScreen';
import AuctionDraftScreen from '../screens/AuctionDraftScreen';
import TradeBlockScreen from '../screens/TradeBlockScreen';
import WaiversScreen from '../screens/WaiversScreen';
import RosterScreen from '../screens/RosterScreen';
import StandingsScreen from '../screens/StandingsScreen';
import SalaryCapScreen from '../screens/SalaryCapScreen';
import ActivityFeedScreen from '../screens/ActivityFeedScreen';
import NotificationsScreen from '../screens/NotificationsScreen';
import ProfileScreen from '../screens/ProfileScreen';
import MatchupScreen from '../screens/MatchupScreen';
import ChatScreen from '../screens/ChatScreen';
import TradeAnalyzerScreen from '../screens/TradeAnalyzerScreen';
import ProjectionsScreen from '../screens/ProjectionsScreen';
import { useChatUnread } from '../hooks/useChatUnread';

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();
const AuthStack = createNativeStackNavigator();

function AuthNavigator() {
  return (
    <AuthStack.Navigator screenOptions={{ headerShown: false }}>
      <AuthStack.Screen name="Login" component={LoginScreen} />
      <AuthStack.Screen name="Register" component={RegisterScreen} />
    </AuthStack.Navigator>
  );
}

function HomeStack() {
  return (
    <Stack.Navigator screenOptions={{
      headerStyle: { backgroundColor: '#141414' },
      headerTintColor: '#fff',
      headerTitleStyle: { fontWeight: 'bold' },
    }}>
      <Stack.Screen name="Dashboard" component={DashboardScreen} />
      <Stack.Screen name="LeagueDetail" component={LeaguesScreen} />
      <Stack.Screen name="StandingsDetail" component={StandingsScreen} />
      <Stack.Screen name="Notifications" component={NotificationsScreen} />
      <Stack.Screen name="Profile" component={ProfileScreen} options={{ title: 'My Profile' }} />
      <Stack.Screen name="Matchup" component={MatchupScreen} options={{ title: 'Matchups' }} />
    </Stack.Navigator>
  );
}

function PlayersStack() {
  return (
    <Stack.Navigator screenOptions={{
      headerStyle: { backgroundColor: '#141414' },
      headerTintColor: '#fff',
    }}>
      <Stack.Screen name="PlayersList" component={PlayersScreen} options={{ title: 'Players' }} />
      <Stack.Screen name="PlayerDetail" component={PlayerDetailScreen} />
      <Stack.Screen name="DraftRoom" component={DraftRoomScreen} />
      <Stack.Screen name="AuctionDraft" component={AuctionDraftScreen} />
    </Stack.Navigator>
  );
}

function LeagueStack() {
  return (
    <Stack.Navigator screenOptions={{
      headerStyle: { backgroundColor: '#141414' },
      headerTintColor: '#fff',
    }}>
      <Stack.Screen name="Roster" component={RosterScreen} />
      <Stack.Screen name="Matchup" component={MatchupScreen} />
      <Stack.Screen name="TradeBlock" component={TradeBlockScreen} />
      <Stack.Screen name="Waivers" component={WaiversScreen} />
      <Stack.Screen name="SalaryCap" component={SalaryCapScreen} />
      <Stack.Screen name="TradeAnalyzer" component={TradeAnalyzerScreen} options={{ title: 'Trade Analyzer' }} />
      <Stack.Screen name="Projections" component={ProjectionsScreen} options={{ title: 'Projections' }} />
    </Stack.Navigator>
  );
}

function ChatStack() {
  return (
    <Stack.Navigator screenOptions={{
      headerStyle: { backgroundColor: '#141414' },
      headerTintColor: '#fff',
    }}>
      <Stack.Screen name="ChatHome" component={ChatScreen} options={{ title: 'League Chat' }} />
    </Stack.Navigator>
  );
}

function ActivityStack() {
  return (
    <Stack.Navigator screenOptions={{
      headerStyle: { backgroundColor: '#141414' },
      headerTintColor: '#fff',
    }}>
      <Stack.Screen name="Activity" component={ActivityFeedScreen} />
      <Stack.Screen name="Standings" component={StandingsScreen} />
    </Stack.Navigator>
  );
}

function MainTabs() {
  const { count: chatUnread } = useChatUnread();
  return (
    <Tab.Navigator screenOptions={{
      headerShown: false,
      tabBarStyle: { backgroundColor: '#141414', borderTopColor: 'rgba(255,255,255,0.1)' },
      tabBarActiveTintColor: '#00D2FF',
      tabBarInactiveTintColor: '#A1A1AA',
    }}>
      <Tab.Screen name="Home" component={HomeStack} options={{ tabBarLabel: 'Home' }} />
      <Tab.Screen name="Players" component={PlayersStack} options={{ tabBarLabel: 'Players' }} />
      <Tab.Screen name="League" component={LeagueStack} options={{ tabBarLabel: 'League' }} />
      <Tab.Screen
        name="Chat"
        component={ChatStack}
        options={{
          tabBarLabel: 'Chat',
          tabBarBadge: chatUnread > 0 ? (chatUnread > 99 ? '99+' : chatUnread) : undefined,
          tabBarBadgeStyle: { backgroundColor: '#FF3B5C', color: '#fff', fontSize: 10 },
        }}
      />
      <Tab.Screen name="Feed" component={ActivityStack} options={{ tabBarLabel: 'Activity' }} />
    </Tab.Navigator>
  );
}

export default function AppNavigator() {
  const { user, loading } = useAuth();

  if (loading) return null; // Splash screen would go here

  return (
    <NavigationContainer ref={navigationRef}>
      {user ? <MainTabs /> : <AuthNavigator />}
    </NavigationContainer>
  );
}
