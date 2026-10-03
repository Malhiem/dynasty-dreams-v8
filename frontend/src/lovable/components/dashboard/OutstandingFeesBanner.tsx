// @ts-nocheck
import { AlertCircle, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { getOutstandingCount, getCurrentUserPaid, getPendingRefunds } from "@/lovable/pages/LeaguePayments";

const OutstandingFeesBanner = () => {
  const outstanding = getOutstandingCount();
  const myPaid = getCurrentUserPaid();
  const pendingRefunds = getPendingRefunds();

  if (outstanding === 0 && pendingRefunds.length === 0) return null;

  return (
    <div className="space-y-3 mb-6">
      {outstanding > 0 && (
        <Link
          to="/payments"
          className="block rounded-lg border border-destructive/30 bg-destructive/5 p-4 hover:bg-destructive/10 transition-colors"
        >
          <div className="flex items-center gap-3">
            <AlertCircle className="h-5 w-5 text-destructive shrink-0" />
            <div className="flex-1">
              <p className="font-semibold text-sm">
                {outstanding} team{outstanding !== 1 ? "s" : ""} still owe admin fees
              </p>
              <p className="text-xs text-muted-foreground">
                {myPaid
                  ? "Your fee is paid. Click to view outstanding payments."
                  : "Your fee is unpaid. Click to make a payment."}
              </p>
            </div>
          </div>
        </Link>
      )}
      {pendingRefunds.length > 0 && (
        <Link
          to="/payments"
          className="block rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 hover:bg-amber-500/10 transition-colors"
        >
          <div className="flex items-center gap-3">
            <ShieldAlert className="h-5 w-5 text-amber-500 shrink-0" />
            <div className="flex-1">
              <p className="font-semibold text-sm">
                {pendingRefunds.length} pending refund{pendingRefunds.length !== 1 ? "s" : ""} — resolve within 1 week to avoid league disruption
              </p>
              <p className="text-xs text-muted-foreground">
                Click to review and refund or hold departing owner fees.
              </p>
            </div>
          </div>
        </Link>
      )}
    </div>
  );
};

export default OutstandingFeesBanner;
