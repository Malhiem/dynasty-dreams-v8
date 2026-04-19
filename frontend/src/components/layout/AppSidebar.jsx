import {
  Home, Users, MessageSquare, Newspaper, ArrowRightLeft, Trophy, DollarSign,
  Star, Clock, Settings, BarChart3, CreditCard, History, Medal, UserSearch,
  Layers, LayoutGrid, ClipboardList, Dices, LogOut, Shield
} from "lucide-react";
import { NavLink } from "@/components/NavLink";
import { useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import {
  Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent,
  SidebarGroupLabel, SidebarMenu, SidebarMenuButton, SidebarMenuItem,
  SidebarHeader, SidebarFooter, useSidebar,
} from "@/components/ui/sidebar";

const mainItems = [
  { title: "Dashboard", url: "/dashboard", icon: Home },
  { title: "Roster", url: "/roster", icon: Users },
  { title: "Standings", url: "/standings", icon: Trophy },
  { title: "Transactions", url: "/transactions", icon: ArrowRightLeft },
];

const socialItems = [
  { title: "Trade Block", url: "/trade-block", icon: ArrowRightLeft },
  { title: "Players", url: "/players", icon: UserSearch },
];

const managementItems = [
  { title: "Scoring", url: "/scoring", icon: Trophy },
  { title: "Salary Cap", url: "/salary-cap", icon: DollarSign },
  { title: "Waivers", url: "/waivers", icon: Clock },
  { title: "Commissioner", url: "/commissioner", icon: Shield },
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

  const isActive = (path) => location.pathname === path;

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
                  {!collapsed && <span>{item.title}</span>}
                </NavLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
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
        {renderGroup("Main", mainItems)}
        {renderGroup("Social", socialItems)}
        {renderGroup("Management", managementItems)}
        {renderGroup("Draft", draftItems)}
      </SidebarContent>

      <SidebarFooter className="p-4 border-t border-white/10">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild isActive={isActive("/leagues")} tooltip="Leagues">
              <NavLink
                to="/leagues"
                className="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors hover:bg-secondary"
                activeClassName="bg-[#00D2FF]/10 text-[#00D2FF]"
              >
                <Settings className="h-4 w-4 shrink-0" />
                {!collapsed && <span>League Settings</span>}
              </NavLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
          {user && (
            <SidebarMenuItem>
              <div className="flex items-center gap-3 px-3 py-2">
                <div className="h-7 w-7 rounded-full bg-[#00D2FF]/20 flex items-center justify-center text-xs font-bold text-[#00D2FF]">
                  {user.name?.[0]?.toUpperCase() || "U"}
                </div>
                {!collapsed && (
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">{user.name}</p>
                    <p className="text-[10px] text-[#A1A1AA] truncate">{user.email}</p>
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
