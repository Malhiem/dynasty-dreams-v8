// @ts-nocheck
/**
 * Iter 229k — `theme_color` rendering. When a team has picked a
 * preset palette (saved via iter 229i), surface it as the chip's
 * background tint. Falls back to the original gradient when no color
 * is set so existing teams render unchanged.
 *
 * Foreground letters auto-flip to white once a color is applied so
 * the abbreviation remains legible on any of the 4 preset hues.
 */
import { cn } from "@/lib/utils";

const sizeClasses = {
  xs: "h-6 w-6 text-[10px]",
  sm: "h-8 w-8 text-xs",
  md: "h-12 w-12 text-sm",
  lg: "h-16 w-16 text-xl",
  xl: "h-20 w-20 text-2xl",
};

interface TeamLogoProps {
  logo?: string;
  name?: string | null;
  abbr?: string;
  size?: keyof typeof sizeClasses;
  className?: string;
  themeColor?: string | null;
}

const TeamLogo = ({ logo, name, abbr, size = "md", className, themeColor }: TeamLogoProps) => {
  // Iter 231n — Playoff brackets contain TBD slots where name is null;
  // guard against null/undefined so the page renders a "TBD" placeholder
  // instead of crashing on `name.split(...)`.
  const safeName = (name && typeof name === "string" ? name : "").trim();
  const initials =
    abbr ||
    (safeName
      ? safeName.split(" ").map((w) => w[0]).filter(Boolean).join("").slice(0, 3).toUpperCase()
      : "TBD");

  if (logo) {
    return (
      <img
        src={logo}
        alt={`${safeName || "Team"} logo`}
        className={cn("rounded-lg object-cover flex-shrink-0", sizeClasses[size], className)}
      />
    );
  }

  const hasTheme = !!themeColor;
  return (
    <div
      className={cn(
        "rounded-lg flex items-center justify-center font-bold flex-shrink-0",
        !hasTheme && "bg-gradient-to-br from-secondary to-muted",
        hasTheme && "text-white drop-shadow",
        sizeClasses[size],
        className,
      )}
      style={hasTheme ? { backgroundColor: themeColor } : undefined}
      data-theme-color={themeColor || undefined}
    >
      {initials}
    </div>
  );
};

export default TeamLogo;
