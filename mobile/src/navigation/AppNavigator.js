import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useAuth } from '../contexts/AuthContext';

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
      <Stack.Screen name="TradeBlock" component={TradeBlockScreen} />
      <Stack.Screen name="Waivers" component={WaiversScreen} />
      <Stack.Screen name="SalaryCap" component={SalaryCapScreen} />
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
      <Tab.Screen name="Feed" component={ActivityStack} options={{ tabBarLabel: 'Activity' }} />
    </Tab.Navigator>
  );
}

export default function AppNavigator() {
  const { user, loading } = useAuth();

  if (loading) return null; // Splash screen would go here

  return (
    <NavigationContainer>
      {user ? <MainTabs /> : <AuthNavigator />}
    </NavigationContainer>
  );
}
