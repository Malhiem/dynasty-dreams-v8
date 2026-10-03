import { useEffect, useState, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { Button } from '@/components/ui/button';
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import api from '@/lib/api';

export default function PaymentSuccessPage() {
  const [params] = useSearchParams();
  const sessionId = params.get('session_id');
  const [status, setStatus] = useState('polling'); // polling | paid | failed | timeout
  const [txn, setTxn] = useState(null);
  const pollRef = useRef(null);
  const attemptsRef = useRef(0);

  useEffect(() => {
    if (!sessionId) {
      setStatus('failed');
      return;
    }
    const poll = async () => {
      attemptsRef.current += 1;
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        setTxn(data);
        if (data.payment_status === 'paid') {
          setStatus('paid');
          clearInterval(pollRef.current);
          return;
        }
        if (data.status === 'expired' || attemptsRef.current >= 10) {
          setStatus('timeout');
          clearInterval(pollRef.current);
        }
      } catch (e) {
        if (attemptsRef.current >= 10) {
          setStatus('failed');
          clearInterval(pollRef.current);
        }
      }
    };
    poll();
    pollRef.current = setInterval(poll, 2000);
    return () => clearInterval(pollRef.current);
  }, [sessionId]);

  return (
    <AppLayout>
      <div
        data-testid="payment-success-page"
        className="max-w-lg mx-auto mt-16 surface p-10 text-center"
      >
        {status === 'polling' && (
          <>
            <Loader2 size={56} className="text-[#00D2FF] mx-auto mb-5 animate-spin" />
            <h1 className="font-heading text-3xl font-bold text-white mb-3">
              CONFIRMING PAYMENT...
            </h1>
            <p className="text-[#A1A1AA]">
              Don't close this page — we're verifying your transaction with Stripe.
            </p>
          </>
        )}

        {status === 'paid' && (
          <>
            <CheckCircle2 size={64} className="text-emerald-400 mx-auto mb-5" />
            <h1 className="font-heading text-3xl font-bold text-white mb-3">
              PAYMENT CONFIRMED
            </h1>
            <p className="text-[#A1A1AA] mb-2">
              ${txn?.amount?.toFixed(2)} {txn?.currency?.toUpperCase()} received.
              Your premium features are now active.
            </p>
            <p className="text-[#52525B] text-xs mb-6">Session: {sessionId}</p>
            <div className="flex gap-3 justify-center">
              <Link to="/commissioner">
                <Button
                  data-testid="payment-success-commissioner-btn"
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
          </>
        )}

        {(status === 'timeout' || status === 'failed') && (
          <>
            <XCircle size={64} className="text-red-400 mx-auto mb-5" />
            <h1 className="font-heading text-3xl font-bold text-white mb-3">
              {status === 'timeout' ? 'STILL PROCESSING' : 'SOMETHING WENT WRONG'}
            </h1>
            <p className="text-[#A1A1AA] mb-6">
              {status === 'timeout'
                ? "Stripe is taking longer than expected. Your league will auto-upgrade once the payment clears — you'll see it on the Commissioner page."
                : "We couldn't verify your payment. If you were charged, it will reflect automatically."}
            </p>
            <Link to="/commissioner">
              <Button className="bg-[#00D2FF] text-black hover:bg-[#33DBFF]">
                Back to Commissioner
              </Button>
            </Link>
          </>
        )}
      </div>
    </AppLayout>
  );
}
