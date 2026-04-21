// @ts-nocheck
import { Button } from "@/components/ui/button";
import { Trophy, Users, RefreshCw, BarChart3, Bell, Settings } from "lucide-react";

const Header = () => {
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-xl">
      <div className="container flex h-16 items-center justify-between">
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/20 border border-primary/30">
              <Trophy className="h-5 w-5 text-primary" />
            </div>
            <span className="font-display text-2xl tracking-wide text-foreground">
              DYNASTY<span className="text-primary">ICE</span>
            </span>
          </div>
          
          <nav className="hidden md:flex items-center gap-1">
            <NavItem icon={<BarChart3 className="h-4 w-4" />} label="Dashboard" active />
            <NavItem icon={<Users className="h-4 w-4" />} label="Team Roster" />
            <NavItem icon={<RefreshCw className="h-4 w-4" />} label="Trades" />
            <NavItem icon={<Trophy className="h-4 w-4" />} label="Standings" />
          </nav>
        </div>

        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" className="relative">
            <Bell className="h-5 w-5" />
            <span className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-primary animate-pulse-glow" />
          </Button>
          <Button variant="ghost" size="icon">
            <Settings className="h-5 w-5" />
          </Button>
          <div className="ml-2 flex items-center gap-3 pl-3 border-l border-border">
            <div className="text-right hidden sm:block">
              <p className="text-sm font-medium">Team Frostbite</p>
              <p className="text-xs text-muted-foreground">Dynasty Pro League</p>
            </div>
            <div className="h-9 w-9 rounded-full bg-gradient-to-br from-primary to-ice-subtle flex items-center justify-center text-sm font-bold text-primary-foreground">
              TF
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

const NavItem = ({ icon, label, active = false }: { icon: React.ReactNode; label: string; active?: boolean }) => (
  <button
    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
      active 
        ? "bg-primary/10 text-primary border-glow" 
        : "text-muted-foreground hover:text-foreground hover:bg-secondary"
    }`}
  >
    {icon}
    {label}
  </button>
);

export default Header;
