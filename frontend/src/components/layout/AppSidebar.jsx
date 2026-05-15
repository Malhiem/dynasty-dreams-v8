import {
  Home, Users, MessageSquare, Newspaper, ArrowRightLeft, Trophy, DollarSign,
  Star, Clock, Settings, BarChart3, CreditCard, History, Medal, UserSearch,
  Layers, LayoutGrid, ClipboardList, Dices, LogOut, Shield, Radio, ScrollText, UserCircle, Flag, Search, Network, Scale
} from "lucide-react";
import { NavLink } from "@/components/NavLink";
import { useLocation, Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import {
  Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent,
  SidebarGroupLabel, SidebarMenu, SidebarMenuButton, SidebarMenuItem,
  SidebarHeader, SidebarFooter, useSidebar,
} from "@/components/ui/sidebar";
import FantasyLevelBadge from "@/components/FantasyLevelBadge";
import { useActiveLeague } from "@/hooks/use-active-league";
import { useChatUnread } from "@/hooks/use-chat-unread";
import CurrentLeagueDropdown from "./CurrentLeagueDropdown";

const userItems = [
  { title: "User Dashboard", url: "/dashboard", icon: UserCircle },
];

// Static items that don't depend on the active league live in this list.
// Dynamic items (League Home, League Administration) are inserted below.
const leagueHubStatic = [
  { title: "Live Scoring", url: "/matchup", icon: Radio },
  { title: "Standings", url: "/standings", icon: Trophy },
  { title: "Transactions", url: "/transactions", icon: ArrowRightLeft },
  { title: "League Information", url: "/league-info", icon: ScrollText },
  { title: "League History", url: "/league-history", icon: History },
  { title: "Trophy Room", url: "/trophy-room", icon: Trophy },
];

const socialItems = [
  { title: "Trade Block", url: "/trade-block", icon: ArrowRightLeft },
  { title: "Chat", url: "/chat", icon: MessageSquare },
];

const managementItems = [
  { title: "Rosters", url: "/roster", icon: Users },
  { title: "Salary Cap", url: "/salary-cap", icon: DollarSign },
  { title: "Waivers / Players", url: "/waivers", icon: Clock },
  { title: "Depth Chart", url: "/depth-chart", icon: Network },
  { title: "Analytics", url: "/analytics", icon: BarChart3 },
  { title: "Trade Analyzer", url: "/trade-analyzer", icon: Scale },
];

const draftItems = [
  { title: "Draft Board", url: "/draft-board", icon: ClipboardList },
  { title: "Draft Room", url: "/draft-room", icon: LayoutGrid },
];

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const location = useLocation();
  const { user, logout } = useAuth();
  const { leagueId: activeLeagueId, league } = useActiveLeague();

  const isActive = (path) => location.pathname === path;
  const { count: chatUnread } = useChatUnread();

  // Determine if the current user is the commissioner OR a co-commissioner
  // for the active league. Used to gate the "League Administration" link.
  const isLeagueAdmin = !!(
    league && user && (
      league.commissioner_id === user.id ||
      (league.co_commissioners || []).includes(user.id)
    )
  );

  // Dynamic League Hub: prepend "League Home" and append "League
  // Administration" only when the user is allowed to administer the league.
  const dynamicLeagueHub = [
    {
      title: "League Home",
      url: activeLeagueId ? `/leagues/${activeLeagueId}` : "/leagues",
      icon: Flag,
    },
    ...leagueHubStatic,
    ...(isLeagueAdmin
      ? [{ title: "League Administration", url: "/commissioner/settings", icon: Shield }]
      : []),
  ];

  const renderGroup = (label, items) => (
    <SidebarGroup>
      <SidebarGroupLabel className="text-muted-foreground text-xs uppercase tracking-wider">
        {!collapsed && label}
      </SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => (
            <SidebarMenuItem key={item.title}>
              <SidebarMenuButton asChild isActive={isActive(item.url)} tooltip={item.title}>
                <NavLink
                  to={item.url}
                  className="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors hover:bg-secondary"
                  activeClassName="bg-[#00D2FF]/10 text-[#00D2FF] border-l-2 border-[#00D2FF]"
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {!collapsed && <span className="flex-1">{item.title}</span>}
                  {item.badge > 0 && (
                    <span
                      data-testid={`sidebar-badge-${item.title.toLowerCase().replace(/\s+/g, "-")}`}
                      className={`ml-auto h-5 ${collapsed ? "absolute right-1 top-1 min-w-[18px]" : "min-w-[20px]"} px-1.5 rounded-full bg-[#FF3B5C] text-white text-[10px] font-bold flex items-center justify-center shadow`}
                    >
                      {item.badge > 99 ? "99+" : item.badge}
                    </span>
                  )}
                </NavLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );

  // Inject the live unread count onto the Chat menu item.
  const socialItemsWithBadge = socialItems.map((it) =>
    it.title === "Chat" ? { ...it, badge: chatUnread } : it,
  );

  return (
    <Sidebar collapsible="icon" className="border-r border-white/10">
      <SidebarHeader className="p-4">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-[#00D2FF]/20 flex items-center justify-center">
            <Trophy className="h-4 w-4 text-[#00D2FF]" />
          </div>
          {!collapsed && (
            <h1 className="font-heading text-lg font-bold tracking-tight text-white">
              DYNASTY<span className="text-[#00D2FF]">DREAMS</span>
            </h1>
          )}
        </div>
      </SidebarHeader>

      <SidebarContent className="px-2">
        {renderGroup("User", userItems)}
        {/* "Current League" switcher — repurposed from the old static
            "Active league" badge that used to live here. Clicking opens
            the league-switch menu; this is the only way to jump between
            leagues besides the User Dashboard link above. */}
        <CurrentLeagueDropdown collapsed={collapsed} />
        {renderGroup("League Hub", dynamicLeagueHub)}
        {renderGroup("Social", socialItemsWithBadge)}
        {renderGroup("Team Management", managementItems)}
        {renderGroup("Draft", draftItems)}
      </SidebarContent>

      <SidebarFooter className="p-4 border-t border-white/10">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild isActive={isActive("/league-search")} tooltip="League Search">
              <NavLink
                to="/league-search"
                data-testid="sidebar-league-search-link"
                className="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors hover:bg-secondary"
                activeClassName="bg-[#00D2FF]/10 text-[#00D2FF]"
              >
                <Search className="h-4 w-4 shrink-0" />
                {!collapsed && <span>League Search</span>}
              </NavLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
          {user && (
            <SidebarMenuItem>
              <div className="flex items-center gap-3 px-3 py-2">
                <Link
                  to={`/profile/edit`}
                  data-testid="sidebar-profile-link"
                  className="h-7 w-7 rounded-full bg-[#00D2FF]/20 flex items-center justify-center text-xs font-bold text-[#00D2FF] hover:ring-2 hover:ring-[#00D2FF]/40 transition-all overflow-hidden"
                  title="Edit your profile"
                >
                  {user.avatar_url ? (
                    <img src={user.avatar_url} alt={user.username} className="h-full w-full object-cover" />
                  ) : (
                    (user.username?.[0] || user.name?.[0] || "U").toUpperCase()
                  )}
                </Link>
                {!collapsed && (
                  <div className="flex-1 min-w-0">
                    <Link
                      to={`/u/${user.username || user.name}`}
                      data-testid="sidebar-username-link"
                      className="text-sm font-medium text-white truncate hover:text-[#00D2FF] block"
                    >
                      {user.username || user.name}
                    </Link>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <FantasyLevelBadge compact />
                    </div>
                  </div>
                )}
                {!collapsed && (
                  <button
                    onClick={logout}
                    className="text-[#A1A1AA] hover:text-white transition-colors"
                    data-testid="sidebar-logout"
                  >
                    <LogOut className="h-4 w-4" />
                  </button>
                )}
              </div>
            </SidebarMenuItem>
          )}
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
