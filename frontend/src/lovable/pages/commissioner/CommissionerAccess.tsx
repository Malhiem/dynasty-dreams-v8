import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/AppLayout";
import { useAuth } from "@/contexts/AuthContext";
import { useActiveLeague } from "@/hooks/use-active-league";
import api from "@/lib/api";

export default function CommissionerAccess({ component: Component }: { component: any }) {
  const leagueContext = useActiveLeague();
  const { user, loading } = useAuth();
  const { leagueId, league } = leagueContext;
  const [access, setAccess] = useState({ key: "", allowed: false });
  const key = `${user?.id || ""}:${leagueId || ""}`;

  useEffect(() => {
    let cancelled = false;
    setAccess({ key: "", allowed: false });
    if (!user?.id || !leagueId) return;
    api.get(`/leagues/${leagueId}`).then(({ data }) => {
      if (!cancelled) setAccess({ key, allowed: data.commissioner_id === user.id });
    }).catch(() => {
      if (!cancelled) setAccess({ key, allowed: false });
    });
    return () => { cancelled = true; };
  }, [key, user?.id, leagueId, league?.commissioner_id]);

  // Never mount administrative effects or controls for an unresolved or denied league.
  if (access.key === key && access.allowed && league?.id === leagueId) {
    return <Component key={key} leagueContext={leagueContext} />;
  }
  const pending = loading || leagueContext.loading || (Boolean(user?.id && leagueId) && access.key !== key);
  return <AppLayout onSettingsClick={undefined}><div className="p-6 space-y-4">
    <h1 className="text-2xl font-bold">League Administration</h1>
    {pending ? <p role="status">Checking league access…</p> :
      <p role="alert">Only the league commissioner can administer this league.</p>}
  </div></AppLayout>;
}
