// @ts-nocheck
import { 
  Home, 
  Users, 
  MessageSquare, 
  Swords, 
  Newspaper, 
  ArrowRightLeft, 
  Trophy, 
  DollarSign, 
  Star, 
  Clock,
  Settings,
  BarChart3,
  CreditCard,
  History,
  Medal,
  UserSearch,
  Layers,
  LayoutGrid,
  ClipboardList,
  Dices
} from "lucide-react";
import { NavLink } from "@/lovable/components/NavLink";
import { useLocation } from "react-router-dom";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  SidebarFooter,
  useSidebar,
} from "@/components/ui/sidebar";

const mainItems = [
  { title: "Dashboard", url: "/", icon: Home },
  { title: "Team Roster", url: "/team", icon: Users },
  { title: "Depth Chart", url: "/depth-chart", icon: Layers },
  { title: "Matchup", url: "/matchup", icon: Swords },
  { title: "Standings", url: "/standings", icon: Trophy },
  { title: "Transactions", url: "/transactions", icon: ArrowRightLeft },
];

const sleeperItems = [
  { title: "League Chat", url: "/chat", icon: MessageSquare, badge: true },
  { title: "Player News", url: "/news", icon: Newspaper },
  { title: "Trade Block", url: "/trade-block", icon: ArrowRightLeft },
];

const fantraxItems = [
  { title: "League Info", url: "/scoring", icon: Trophy },
  { title: "Salary Cap", url: "/salary", icon: DollarSign },
  { title: "Prospects", url: "/prospects", icon: Star },
  { title: "Waivers", url: "/waivers", icon: Clock },
  { title: "Player Pool", url: "/player-pool", icon: UserSearch },
  { title: "Analytics", url: "/analytics", icon: BarChart3 },
  { title: "Payments", url: "/payments", icon: CreditCard },
];

const draftItems = [
  { title: "Draft Board", url: "/draft-board", icon: ClipboardList },
  { title: "Draft Room", url: "/draft-room", icon: LayoutGrid },
  { title: "Draft Lottery", url: "/draft-lottery", icon: Dices },
];

const historyItems = [
  { title: "League History", url: "/league-history", icon: History },
  { title: "Franchise Records", url: "/franchise-records", icon: Medal },
];

import { useChatUnread } from "@/hooks/use-chat-unread";

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const { count: CHAT_UNREAD_COUNT } = useChatUnread();
  const location = useLocation();
  const currentPath = location.pathname;

  const isActive = (path: string) => currentPath === path;

  return (
    <Sidebar collapsible="icon" className="border-r border-border">
      <SidebarHeader className="p-4">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-primary/20 flex items-center justify-center">
            <span className="text-primary font-bold text-sm">🏒</span>
          </div>
          {!collapsed && (
            <div>
              <h1 className="font-display text-xl tracking-wide text-foreground">
                DYNASTY<span className="text-primary">ICE</span>
              </h1>
            </div>
          )}
        </div>
      </SidebarHeader>

      <SidebarContent className="px-2">
        <SidebarGroup>
          <SidebarGroupLabel className="text-muted-foreground text-xs uppercase tracking-wider">
            {!collapsed && "Main"}
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {mainItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton 
                    asChild 
                    isActive={isActive(item.url)}
                    tooltip={item.title}
                  >
                    <NavLink 
                      to={item.url} 
                      className="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors hover:bg-secondary"
                      activeClassName="bg-primary/10 text-primary border-l-2 border-primary"
                    >
                      <item.icon className="h-4 w-4 shrink-0" />
                      {!collapsed && <span>{item.title}</span>}
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel className="text-muted-foreground text-xs uppercase tracking-wider">
            {!collapsed && "Social"}
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {sleeperItems.map((item) => {
                const unread = (item as any).badge ? CHAT_UNREAD_COUNT : 0;
                const displayCount = unread > 9 ? "9+" : unread;
                return (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton 
                      asChild 
                      isActive={isActive(item.url)}
                      tooltip={item.title}
                    >
                      <NavLink 
                        to={item.url} 
                        className="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors hover:bg-secondary"
                        activeClassName="bg-primary/10 text-primary border-l-2 border-primary"
                      >
                        <div className="relative shrink-0">
                          <item.icon className="h-4 w-4" />
                          {unread > 0 && collapsed && (
                            <span className="absolute -top-1.5 -right-1.5 h-4 min-w-4 px-1 rounded-full bg-primary text-primary-foreground text-[10px] font-medium flex items-center justify-center">
                              {displayCount}
                            </span>
                          )}
                        </div>
                        {!collapsed && (
                          <>
                            <span className="flex-1">{item.title}</span>
                            {unread > 0 && (
                              <span className="h-5 min-w-5 px-1.5 rounded-full bg-primary text-primary-foreground text-xs font-medium flex items-center justify-center">
                                {displayCount}
                              </span>
                            )}
                          </>
                        )}
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel className="text-muted-foreground text-xs uppercase tracking-wider">
            {!collapsed && "Management"}
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {fantraxItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton 
                    asChild 
                    isActive={isActive(item.url)}
                    tooltip={item.title}
                  >
                    <NavLink 
                      to={item.url} 
                      className="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors hover:bg-secondary"
                      activeClassName="bg-primary/10 text-primary border-l-2 border-primary"
                    >
                      <item.icon className="h-4 w-4 shrink-0" />
                      {!collapsed && <span>{item.title}</span>}
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel className="text-muted-foreground text-xs uppercase tracking-wider">
            {!collapsed && "Draft"}
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {draftItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton 
                    asChild 
                    isActive={isActive(item.url)}
                    tooltip={item.title}
                  >
                    <NavLink 
                      to={item.url} 
                      className="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors hover:bg-secondary"
                      activeClassName="bg-primary/10 text-primary border-l-2 border-primary"
                    >
                      <item.icon className="h-4 w-4 shrink-0" />
                      {!collapsed && <span>{item.title}</span>}
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel className="text-muted-foreground text-xs uppercase tracking-wider">
            {!collapsed && "History"}
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {historyItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton 
                    asChild 
                    isActive={isActive(item.url)}
                    tooltip={item.title}
                  >
                    <NavLink 
                      to={item.url} 
                      className="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors hover:bg-secondary"
                      activeClassName="bg-primary/10 text-primary border-l-2 border-primary"
                    >
                      <item.icon className="h-4 w-4 shrink-0" />
                      {!collapsed && <span>{item.title}</span>}
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-4 border-t border-border">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton 
              asChild 
              isActive={isActive("/commissioner/settings")}
              tooltip="League Administration"
            >
              <NavLink 
                to="/commissioner/settings" 
                className="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors hover:bg-secondary"
                activeClassName="bg-primary/10 text-primary"
              >
                <Settings className="h-4 w-4 shrink-0" />
                {!collapsed && <span>League Administration</span>}
              </NavLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton 
              asChild 
              isActive={isActive("/teams-owners")}
              tooltip="Teams & Owners"
            >
              <NavLink 
                to="/teams-owners" 
                className="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors hover:bg-secondary"
                activeClassName="bg-primary/10 text-primary"
              >
                <Users className="h-4 w-4 shrink-0" />
                {!collapsed && <span>Teams & Owners</span>}
              </NavLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
