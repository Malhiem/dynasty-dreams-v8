export function StatCard({ label, value, icon: Icon, trend, trendUp }) {
  return (
    <div className="surface p-6 h-full" data-testid={`stat-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className="flex items-start justify-between mb-4">
        <span className="stat-label">{label}</span>
        {Icon && <Icon size={24} weight="duotone" className="text-[#00D2FF]" />}
      </div>
      <div className="stat-value">{value}</div>
      {trend && (
        <div className={`mt-2 text-sm font-medium ${trendUp ? 'text-[#34C759]' : 'text-[#FF3B30]'}`}>
          {trendUp ? '↑' : '↓'} {trend}
        </div>
      )}
    </div>
  );
}
