// @ts-nocheck
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
  name: string;
  abbr?: string;
  size?: keyof typeof sizeClasses;
  className?: string;
}

const TeamLogo = ({ logo, name, abbr, size = "md", className }: TeamLogoProps) => {
  const initials = abbr || name.split(" ").map(w => w[0]).join("").slice(0, 3).toUpperCase();

  if (logo) {
    return (
      <img
        src={logo}
        alt={`${name} logo`}
        className={cn("rounded-lg object-cover flex-shrink-0", sizeClasses[size], className)}
      />
    );
  }

  return (
    <div
      className={cn(
        "rounded-lg bg-gradient-to-br from-secondary to-muted flex items-center justify-center font-bold flex-shrink-0",
        sizeClasses[size],
        className
      )}
    >
      {initials}
    </div>
  );
};

export default TeamLogo;
