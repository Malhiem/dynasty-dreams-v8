import { useEffect, useMemo, useState } from "react";
import {
  Home, Users, MessageSquare, Newspaper, ArrowRightLeft, Trophy, DollarSign,
  Star, Clock, Settings, BarChart3, CreditCard, History, Medal, UserSearch,
  Layers, LayoutGrid, ClipboardList, Dices, LogOut, Shield, Radio, ScrollText,
  UserCircle, Flag, Search, Network, Scale, ChevronDown, ChevronRight, GripVertical,
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
import { usePendingWaivers } from "@/hooks/use-pending-waivers";
import CurrentLeagueDropdown from "./CurrentLeagueDropdown";

const userItems = [
  { title: "User Dashboard", url: "/dashboard", icon: UserCircle },
];

const adminItem = { title: "Admin Dashboard", url: "/admin", icon: Shield };

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
  { title: "Forum", url: "/forum", icon: Newspaper },
];

const managementItems = [
  { title: "Rosters", url: "/roster", icon: Users },
  { title: "Salary Cap", url: "/salary-cap", icon: DollarSign },
  // Iter 232N.9 — Free Agents unifies Players + Waiver claim management.
  // Label keeps both legacy terms so managers used to "Waivers / Players"
  // still recognise the entry after the URL migration to /players.
  { title: "Free Agents / Waivers", url: "/players", icon: Clock },
  { title: "Depth Chart", url: "/depth-chart", icon: Network },
  { title: "Analytics", url: "/analytics", icon: BarChart3 },
  { title: "Trade Analyzer", url: "/trade-analyzer", icon: Scale },
];

const draftItems = [
  { title: "Draft Board", url: "/draft-board", icon: ClipboardList },
  { title: "Draft Room", url: "/draft-room", icon: LayoutGrid },
  { title: "Draft History", url: "/draft-history", icon: History },
];

// Iter 231p — Sidebar group registry. Each group has a stable `key`
// (used for localStorage persistence of order + collapsed state) plus
// its display label and items. The User group is intentionally NOT in
// this list — it stays pinned to the top (and includes the league
// switcher) so users can always return to the dashboard / change
// leagues regardless of how they've reordered everything else.
const SIDEBAR_GROUPS_LS_ORDER = "dd_sidebar_group_order_v1";
const SIDEBAR_GROUPS_LS_COLLAPSED = "dd_sidebar_group_collapsed_v1";
const DEFAULT_GROUP_ORDER = ["league_hub", "social", "team_mgmt", "draft"];

function loadOrder() {
  try {
    const raw = localStorage.getItem(SIDEBAR_GROUPS_LS_ORDER);
    if (!raw) return DEFAULT_GROUP_ORDER;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return DEFAULT_GROUP_ORDER;
    // Drop unknown keys + append any missing defaults so newly-added
    // groups still appear after a future release.
    const known = new Set(DEFAULT_GROUP_ORDER);
    const cleaned = parsed.filter((k) => known.has(k));
    for (const k of DEFAULT_GROUP_ORDER) if (!cleaned.includes(k)) cleaned.push(k);
    return cleaned;
  } catch {
    return DEFAULT_GROUP_ORDER;
  }
}

function loadCollapsed() {
  try {
    const raw = localStorage.getItem(SIDEBAR_GROUPS_LS_COLLAPSED);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const location = useLocation();
  const { user, logout } = useAuth();
  const { leagueId: activeLeagueId, league } = useActiveLeague();

  const isActive = (path) => location.pathname === path;
  const { count: chatUnread } = useChatUnread();
  // Iter 232N.9 — Pending waiver claims count feeds a red badge on the
  // Free Agents nav link so managers see actionable state at a glance.
  const { count: pendingWaivers } = usePendingWaivers();

  // Iter 231p — Persisted per-user customisation (order + collapse).
  const [groupOrder, setGroupOrder] = useState(loadOrder);
  const [collapsedMap, setCollapsedMap] = useState(loadCollapsed);
  const [dragKey, setDragKey] = useState(null);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_GROUPS_LS_ORDER, JSON.stringify(groupOrder));
  }, [groupOrder]);
  useEffect(() => {
    localStorage.setItem(SIDEBAR_GROUPS_LS_COLLAPSED, JSON.stringify(collapsedMap));
  }, [collapsedMap]);

  const isLeagueAdmin = !!(
    league && user && (
      league.commissioner_id === user.id ||
      (league.co_commissioners || []).includes(user.id)
    )
  );

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

  const socialItemsWithBadge = socialItems.map((it) =>
    it.title === "Chat" ? { ...it, badge: chatUnread } : it,
  );

  // Iter 232N.9 — Attach pending-claims badge to the Free Agents link.
  const managementItemsWithBadge = managementItems.map((it) =>
    it.title === "Free Agents / Waivers" ? { ...it, badge: pendingWaivers } : it,
  );

  // Iter 231p — Resolved group registry keyed by stable `key`. Order
  // applied below via `groupOrder`.
  const groupRegistry = useMemo(() => ({
    league_hub: { key: "league_hub", label: "League Hub", items: dynamicLeagueHub },
    social: { key: "social", label: "Social", items: socialItemsWithBadge },
    team_mgmt: { key: "team_mgmt", label: "Team Management", items: managementItemsWithBadge },
    draft: { key: "draft", label: "Draft", items: draftItems },
  }), [dynamicLeagueHub, socialItemsWithBadge, managementItemsWithBadge]);

  const toggleCollapsed = (key) => {
    setCollapsedMap((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // ── Drag-and-drop reorder (HTML5; same pattern as MyLeagues) ─────
  const onDragStart = (key) => (e) => {
    setDragKey(key);
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", key); } catch { /* noop */ }
  };
  const onDragOver = (key) => (e) => {
    e.preventDefault();
    if (!dragKey || dragKey === key) return;
    setGroupOrder((prev) => {
      const next = [...prev];
      const from = next.indexOf(dragKey);
      const to = next.indexOf(key);
      if (from < 0 || to < 0) return prev;
      next.splice(to, 0, next.splice(from, 1)[0]);
      return next;
    });
  };
  const onDragEnd = () => setDragKey(null);

  const renderItem = (item) => (
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
  );

  const renderStaticGroup = (label, items) => (
    <SidebarGroup>
      <SidebarGroupLabel className="text-muted-foreground text-xs uppercase tracking-wider">
        {!collapsed && label}
      </SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>{items.map(renderItem)}</SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );

  // Iter 231p — Reorderable + collapsible group renderer. Header click
  // toggles items; the grip handle (visible on hover) starts a drag to
  // reorder. In collapsed-sidebar mode we suppress the drag affordance
  // entirely (no room to render it).
  const renderReorderableGroup = (group) => {
    const isCollapsed = !!collapsedMap[group.key];
    const isDragging = dragKey === group.key;
    return (
      <SidebarGroup
        key={group.key}
        draggable={!collapsed}
        onDragStart={onDragStart(group.key)}
        onDragOver={onDragOver(group.key)}
        onDragEnd={onDragEnd}
        className={isDragging ? "opacity-50" : ""}
        data-testid={`sidebar-group-${group.key}`}
      >
        <SidebarGroupLabel asChild>
          <button
            type="button"
            onClick={() => toggleCollapsed(group.key)}
            className="group flex w-full items-center gap-1.5 text-muted-foreground text-xs uppercase tracking-wider hover:text-white transition-colors"
            data-testid={`sidebar-group-toggle-${group.key}`}
            aria-expanded={!isCollapsed}
          >
            {!collapsed && (
              <>
                {isCollapsed ? (
                  <ChevronRight className="h-3 w-3 shrink-0" />
                ) : (
                  <ChevronDown className="h-3 w-3 shrink-0" />
                )}
                <span className="flex-1 text-left">{group.label}</span>
                <GripVertical
                  className="h-3 w-3 opacity-0 group-hover:opacity-60 cursor-grab active:cursor-grabbing"
                  aria-hidden
                />
              </>
            )}
          </button>
        </SidebarGroupLabel>
        {!isCollapsed && (
          <SidebarGroupContent>
            <SidebarMenu>{group.items.map(renderItem)}</SidebarMenu>
          </SidebarGroupContent>
        )}
      </SidebarGroup>
    );
  };

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
        {/* User group + league switcher are pinned (not reorderable). */}
        {renderStaticGroup("User", user?.role === "admin" ? [...userItems, adminItem] : userItems)}
        <CurrentLeagueDropdown collapsed={collapsed} />
        {/* Iter 231p — Reorderable + collapsible groups. */}
        {groupOrder.map((key) => groupRegistry[key]).filter(Boolean).map(renderReorderableGroup)}
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
                    aria-label="Sign out"
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
