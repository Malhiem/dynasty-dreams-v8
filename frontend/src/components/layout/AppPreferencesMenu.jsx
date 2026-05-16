import { Settings, Sun, Moon, Monitor } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/hooks/use-theme";

/**
 * Cog dropdown in the header that hosts the app theme toggle (and any
 * future global preferences). Persists the active theme via `useTheme` —
 * the choice survives reloads.
 */
export default function AppPreferencesMenu() {
  const { theme, setTheme } = useTheme();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          data-testid="app-preferences-cog"
          title="App preferences"
          className="text-muted-foreground hover:text-foreground hover:bg-white/5 dark:hover:bg-white/5 h-9 w-9"
        >
          <Settings className="h-5 w-5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="w-56"
        data-testid="app-preferences-menu"
      >
        <DropdownMenuLabel className="text-xs uppercase tracking-wider text-muted-foreground">
          Appearance
        </DropdownMenuLabel>
        <DropdownMenuItem
          onClick={() => setTheme("dark")}
          data-testid="theme-option-dark"
          className={theme === "dark" ? "bg-secondary" : ""}
        >
          <Moon className="h-4 w-4 mr-2" />
          <span>Dark</span>
          {theme === "dark" && (
            <span
              className="ml-auto text-[10px] text-primary"
              data-testid="theme-active-dark"
            >
              ACTIVE
            </span>
          )}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => setTheme("light")}
          data-testid="theme-option-light"
          className={theme === "light" ? "bg-secondary" : ""}
        >
          <Sun className="h-4 w-4 mr-2" />
          <span>Light</span>
          {theme === "light" && (
            <span
              className="ml-auto text-[10px] text-primary"
              data-testid="theme-active-light"
            >
              ACTIVE
            </span>
          )}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled>
          <Monitor className="h-4 w-4 mr-2" />
          <span className="text-xs text-muted-foreground">
            More preferences soon
          </span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
