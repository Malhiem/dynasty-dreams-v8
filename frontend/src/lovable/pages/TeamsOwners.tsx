// @ts-nocheck
/**
 * Iter 231z — Replaced the iter 226 mocked stub with the live
 * `TeamsTab` component used inside League Administration.
 *
 * The previous version of this file rendered a hardcoded
 * `initialOwners` array of 12 mocked teams and bound the trash icon to
 * `setOwners(prev => prev.filter(...))` — i.e. local-React-state
 * removal with no API call. That's why the "Revoke invite" button
 * on the sidebar's Teams & Owners route silently no-op'd: the
 * page itself had no idea what an invite was.
 *
 * The real, live, API-backed Teams & Owners experience lives in
 * `components/admin/TeamsTab.tsx` (iter 228z). This page now wraps
 * that same component inside the AppLayout shell so the sidebar
 * link finally drives the right UX, with the working AlertDialog
 * + DELETE /api/team-invites/{id} integration introduced in iter
 * 231p, the safety guard from iter 231x (team_id-based lookup),
 * and the recent test_iter231p / iter231x regression coverage.
 */
import { AppLayout } from "@/components/layout/AppLayout";
import TeamsTab from "@/lovable/components/admin/TeamsTab";

const TeamsOwners = () => {
  return (
    <AppLayout>
      <div className="p-6" data-testid="teams-owners-page">
        <TeamsTab />
      </div>
    </AppLayout>
  );
};

export default TeamsOwners;
