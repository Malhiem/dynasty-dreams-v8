// @ts-nocheck
import { LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  trend?: {
    value: number;
    positive: boolean;
  };
  highlight?: boolean;
}

const StatCard = ({ title, value, subtitle, icon: Icon, trend, highlight }: StatCardProps) => {
  return (
    <div className={`stat-card group hover:border-primary/30 transition-all duration-300 ${highlight ? 'glow-ice' : ''}`}>
      <div className="flex items-start justify-between mb-4">
        <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${
          highlight ? 'bg-primary/20 text-primary' : 'bg-secondary text-muted-foreground'
        } group-hover:scale-110 transition-transform duration-300`}>
          <Icon className="h-5 w-5" />
        </div>
        {trend && (
          <span className={`text-xs font-medium px-2 py-1 rounded-full ${
            trend.positive ? 'bg-success/20 text-success' : 'bg-destructive/20 text-destructive'
          }`}>
            {trend.positive ? '+' : ''}{trend.value}%
          </span>
        )}
      </div>
      
      <p className="text-sm text-muted-foreground mb-1">{title}</p>
      <p className={`text-3xl font-bold ${highlight ? 'text-gradient-ice' : 'text-foreground'}`}>
        {value}
      </p>
      {subtitle && (
        <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
      )}
    </div>
  );
};

export default StatCard;
