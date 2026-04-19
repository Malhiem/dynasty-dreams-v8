import { Link } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { Button } from '@/components/ui/button';
import { AlertTriangle } from 'lucide-react';

export default function PaymentCancelPage() {
  return (
    <AppLayout>
      <div
        data-testid="payment-cancel-page"
        className="max-w-lg mx-auto mt-16 surface p-10 text-center"
      >
        <AlertTriangle size={56} className="text-yellow-400 mx-auto mb-5" />
        <h1 className="font-heading text-3xl font-bold text-white mb-3">
          PAYMENT CANCELLED
        </h1>
        <p className="text-[#A1A1AA] mb-6">
          No charges were made. You can upgrade your league to premium anytime from the
          Commissioner page.
        </p>
        <div className="flex gap-3 justify-center">
          <Link to="/commissioner">
            <Button
              data-testid="payment-cancel-retry-btn"
              className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]"
            >
              Back to Commissioner
            </Button>
          </Link>
          <Link to="/dashboard">
            <Button
              variant="outline"
              className="border-white/10 text-white hover:bg-white/5"
            >
              Dashboard
            </Button>
          </Link>
        </div>
      </div>
    </AppLayout>
  );
}
