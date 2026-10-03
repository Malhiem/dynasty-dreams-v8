// @ts-nocheck
/**
 * 404 page — Iter 225 hardening.
 *  • Logs the bad path for analytics.
 *  • Uses SOFT navigation (useNavigate) so the auth context isn't blown away.
 *  • "Go back" pops the history stack (location is replaced so the dead
 *    route isn't re-entered); "Go to dashboard" is the safe fallback.
 */
import { useLocation, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";

const NotFound = () => {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  const goBack = () => {
    // -1 falls back to dashboard if the user landed here directly.
    if (window.history.length > 1) {
      navigate(-1);
    } else {
      navigate("/dashboard", { replace: true });
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted">
      <div className="text-center max-w-md px-6" data-testid="not-found-page">
        <h1 className="mb-2 text-5xl font-bold">404</h1>
        <p className="mb-1 text-xl text-muted-foreground">Page not found</p>
        <p className="mb-6 text-xs text-muted-foreground/80">
          We couldn&apos;t find <code className="text-foreground/90">{location.pathname}</code>.
        </p>
        <div className="flex gap-2 justify-center">
          <Button onClick={goBack} variant="default" data-testid="not-found-back-btn">
            Go back
          </Button>
          <Button
            onClick={() => navigate("/dashboard", { replace: true })}
            variant="outline"
            data-testid="not-found-dashboard-btn"
          >
            Go to dashboard
          </Button>
        </div>
      </div>
    </div>
  );
};

export default NotFound;
