import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "./AppSidebar";
import { Search, Bell } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function AppLayout({ children }) {
  const { user } = useAuth();

  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full bg-[#0A0A0A]">
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <header className="h-14 border-b border-white/10 flex items-center justify-between px-4 bg-[#141414]/80 backdrop-blur-sm sticky top-0 z-10">
            <div className="flex items-center gap-4">
              <SidebarTrigger className="text-[#A1A1AA] hover:text-white" data-testid="sidebar-trigger" />
              <div className="relative hidden md:block">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#A1A1AA]" />
                <Input
                  placeholder="Search players, teams..."
                  className="pl-9 w-64 bg-[#1A1A1A] border-white/10 text-white placeholder:text-[#52525B] focus:border-[#00D2FF]"
                  data-testid="header-search"
                />
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Button variant="ghost" size="icon" className="relative text-[#A1A1AA] hover:text-white" data-testid="notifications-btn">
                <Bell className="h-5 w-5" />
                <span className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-[#00D2FF] animate-pulse" />
              </Button>
              {user && (
                <div className="flex items-center gap-3 pl-3 border-l border-white/10">
                  <div className="text-right hidden sm:block">
                    <p className="text-sm font-medium text-white">{user.name}</p>
                    <p className="text-xs text-[#A1A1AA]">{user.role}</p>
                  </div>
                  <div className="h-9 w-9 rounded-full bg-[#00D2FF]/20 flex items-center justify-center text-sm font-bold text-[#00D2FF]">
                    {user.name?.[0]?.toUpperCase() || "U"}
                  </div>
                </div>
              )}
            </div>
          </header>
          <main className="flex-1 overflow-auto p-6">
            {children}
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
