// @ts-nocheck
import { DollarSign } from "lucide-react";

const formatCurrency = (val: number) => `$${(val / 1000000).toFixed(1)}M`;

const TeamSalaryCap = () => {
  const capLimit = 88000000;
  const capUsed = 92516953;
  const retainedSalary = 2500000;
  const capRemaining = capLimit - capUsed;
  const retentionSlotsTotal = 3;
  const retentionSlotsUsed = 1;
  const retentionSlotsRemaining = retentionSlotsTotal - retentionSlotsUsed;
  const overCap = capRemaining < 0;

  const items = [
    { label: "Cap Limit", value: formatCurrency(capLimit), accent: false },
    { label: "Cap Used", value: formatCurrency(capUsed), accent: false },
    {
      label: "Cap Remaining",
      value: formatCurrency(Math.abs(capRemaining)),
      accent: true,
      negative: overCap,
    },
    {
      label: "Retention Slots Remaining",
      value: `${retentionSlotsRemaining} / ${retentionSlotsTotal}`,
      accent: false,
    },
    { label: "Retained Salary", value: formatCurrency(retainedSalary), accent: false },
  ];

  return (
    <div className="stat-card p-0 overflow-hidden">
      <div className="p-6 border-b border-border">
        <div className="flex items-center gap-2">
          <DollarSign className="h-5 w-5 text-accent" />
          <h3 className="text-lg font-semibold">Salary Cap</h3>
        </div>
      </div>

      <div className="p-6">
        {/* Cap bar */}
        <div className="mb-6">
          <div className="flex justify-between text-xs text-muted-foreground mb-2">
            <span>Used: {formatCurrency(capUsed)}</span>
            <span>Limit: {formatCurrency(capLimit)}</span>
          </div>
          <div className="h-3 rounded-full bg-secondary overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${overCap ? "bg-destructive" : "bg-primary"}`}
              style={{ width: `${Math.min((capUsed / capLimit) * 100, 100)}%` }}
            />
          </div>
          {overCap && (
            <p className="text-xs text-destructive mt-1 font-medium">
              Over cap by {formatCurrency(Math.abs(capRemaining))}
            </p>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          {items.map((item) => (
            <div key={item.label} className="text-center p-3 rounded-lg bg-secondary/30">
              <p className="text-xs text-muted-foreground mb-1">{item.label}</p>
              <p
                className={`text-sm font-bold ${
                  item.accent
                    ? item.negative
                      ? "text-destructive"
                      : "text-success"
                    : "text-foreground"
                }`}
              >
                {item.negative ? "-" : ""}
                {item.value}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default TeamSalaryCap;
