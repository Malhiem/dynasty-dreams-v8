// @ts-nocheck
/**
 * UserExtensionsSection — 5-section expanded read-out for the User Detail Drawer.
 * Extracted from AdminDashboard.tsx during Iter 222 refactor.
 *
 * Sections: League & Team Relationships · Behavioral & Moderation ·
 *           Financial / Billing · Support & Engagement · Compliance & Legal.
 */
import { DetailGrid, DetailRow } from "./_shared";

export function UserExtensionsSection({ detail }) {
  return (
    <>
      <ExtSection title="League & Team Relationships" testid="ext-league-team">
        <ExtSubTitle>Leagues joined · {detail.leagues_joined?.length || 0}</ExtSubTitle>
        {detail.leagues_joined?.length === 0 ? (
          <ExtEmpty>No league memberships</ExtEmpty>
        ) : (
          <ExtTable head={["League", "Role", "Status", "Joined"]}>
            {(detail.leagues_joined || []).slice(0, 15).map((l) => (
              <tr key={l.league_id} className="border-t border-border/40">
                <td className="px-2 py-1 max-w-[200px] truncate" title={l.league_name}>{l.league_name || "—"}</td>
                <td className="px-2 py-1">
                  <RoleBadge role={l.role} />
                </td>
                <td className="px-2 py-1 text-muted-foreground">{l.league_status || "—"}</td>
                <td className="px-2 py-1 text-muted-foreground whitespace-nowrap">
                  {l.joined_at ? new Date(l.joined_at).toLocaleDateString() : "—"}
                </td>
              </tr>
            ))}
          </ExtTable>
        )}
        <ExtSubTitle>Teams owned (current · {detail.teams_owned?.length || 0})</ExtSubTitle>
        {detail.teams_owned?.length === 0 ? (
          <ExtEmpty>No teams owned</ExtEmpty>
        ) : (
          <ul className="text-xs space-y-0.5">
            {(detail.teams_owned || []).slice(0, 10).map((t) => (
              <li key={t.team_id} className="flex gap-2">
                <span className="text-foreground/90 truncate max-w-[200px]">{t.team_name || "—"}</span>
                <span className="text-muted-foreground">·</span>
                <span className="text-muted-foreground truncate max-w-[200px]">{t.league_name || "—"}</span>
              </li>
            ))}
          </ul>
        )}
        {(detail.teams_owned_history?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Teams owned (historical · {detail.teams_owned_history.length})</ExtSubTitle>
            <ul className="text-xs space-y-0.5 text-muted-foreground">
              {detail.teams_owned_history.slice(0, 10).map((t) => (
                <li key={t.team_id}>{t.team_name} · {t.league_name || "—"}</li>
              ))}
            </ul>
          </>
        )}
        {(detail.invitations_sent?.length || 0) + (detail.invitations_received?.length || 0) > 0 && (
          <DetailGrid>
            <DetailRow k="Invitations sent" v={`${detail.invitations_sent?.length || 0}`} />
            <DetailRow k="Invitations received" v={`${detail.invitations_received?.length || 0}`} />
          </DetailGrid>
        )}
      </ExtSection>

      <ExtSection title="Behavioral & Moderation" testid="ext-behavioral">
        <DetailGrid>
          <DetailRow k="Reports filed against user" v={`${detail.reports_against_count ?? 0}`} />
          <DetailRow k="Reports filed by user" v={`${detail.reports_filed_count ?? 0}`} />
          <DetailRow k="Trade flags" v={`${detail.trade_flags_count ?? 0}`} />
          <DetailRow k="Chat / content violations" v={`${detail.chat_violations_count ?? 0}`} />
          <DetailRow k="Trust score" v={detail.trust_score != null ? String(detail.trust_score) : "—"} />
          <DetailRow k="On watchlist" v={detail.watchlist
            ? <span className="text-amber-300">yes — {detail.watchlist_reason || "no reason"}</span>
            : "no"} />
        </DetailGrid>
        {(detail.multi_account_links?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Multi-account linkage flags</ExtSubTitle>
            <ul className="text-xs space-y-0.5">
              {detail.multi_account_links.map((m, i) => (
                <li key={i} className="text-amber-300">
                  Device hash <code>{m.device_hash}</code> shared with {m.linked_user_ids.length} other account(s)
                </li>
              ))}
            </ul>
          </>
        )}
        {(detail.moderation_action_history?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Moderation action history</ExtSubTitle>
            <ExtTable head={["Action", "Reason", "By", "When", "Appealed"]}>
              {detail.moderation_action_history.slice(0, 15).map((m) => (
                <tr key={m.id} className="border-t border-border/40">
                  <td className="px-2 py-1 font-mono">{m.action}</td>
                  <td className="px-2 py-1 italic text-foreground/80 max-w-[200px] truncate" title={m.reason}>{m.reason || "—"}</td>
                  <td className="px-2 py-1 text-muted-foreground truncate max-w-[160px]">{m.admin_email}</td>
                  <td className="px-2 py-1 text-muted-foreground whitespace-nowrap">{m.ts ? new Date(m.ts).toLocaleDateString() : "—"}</td>
                  <td className="px-2 py-1">{m.appealed ? <span className="text-amber-300">yes</span> : "no"}</td>
                </tr>
              ))}
            </ExtTable>
          </>
        )}
        {(detail.appeals?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Appeals · {detail.appeals.length}</ExtSubTitle>
            <ul className="text-xs space-y-1">
              {detail.appeals.slice(0, 5).map((a) => (
                <li key={a.id}>
                  <span className={a.status === "approved" ? "text-emerald-300" : a.status === "denied" ? "text-rose-300" : "text-amber-300"}>
                    {a.status}
                  </span>
                  <span className="ml-2 text-muted-foreground">{a.created_at ? new Date(a.created_at).toLocaleDateString() : "—"}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </ExtSection>

      <ExtSection title="Financial / Billing" testid="ext-financial">
        <DetailGrid>
          <DetailRow k="Subscription tier" v={detail.subscription_tier} />
          <DetailRow k="Status" v={detail.subscription_status} />
          <DetailRow k="Promo credits" v={`${((detail.promo_credits_cents || 0) / 100).toFixed(2)} ${detail.payout_info?.currency || "USD"}`} />
          <DetailRow k="Chargebacks" v={detail.chargeback_flags?.length ? <span className="text-rose-300">{detail.chargeback_flags.length}</span> : "0"} />
          <DetailRow k="Payout method" v={detail.payout_info?.method || "—"} />
          <DetailRow k="Tax form" v={detail.payout_info?.tax_form_status || "—"} />
        </DetailGrid>
        {(detail.payment_methods?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Payment methods on file (tokenized · PCI-safe)</ExtSubTitle>
            <ul className="text-xs space-y-0.5">
              {detail.payment_methods.map((pm) => (
                <li key={pm.id}>
                  <span className="font-mono">{pm.brand}</span> · ••••{pm.last4} · exp {pm.exp_month}/{pm.exp_year}
                </li>
              ))}
            </ul>
          </>
        )}
        {(detail.billing_history?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Billing history (last {detail.billing_history.length})</ExtSubTitle>
            <ExtTable head={["When", "Amount", "Status", "Description"]}>
              {detail.billing_history.slice(0, 10).map((b) => (
                <tr key={b.id} className="border-t border-border/40">
                  <td className="px-2 py-1 text-muted-foreground whitespace-nowrap">{b.created_at ? new Date(b.created_at).toLocaleDateString() : "—"}</td>
                  <td className="px-2 py-1">{((b.amount_cents || 0) / 100).toFixed(2)} {(b.currency || "USD").toUpperCase()}</td>
                  <td className="px-2 py-1">{b.status}</td>
                  <td className="px-2 py-1 text-muted-foreground truncate max-w-[180px]">{b.description || "—"}</td>
                </tr>
              ))}
            </ExtTable>
          </>
        )}
        {(detail.league_fees?.length || 0) > 0 && (
          <>
            <ExtSubTitle>League fees · {detail.league_fees.length}</ExtSubTitle>
            <ul className="text-xs space-y-0.5">
              {detail.league_fees.slice(0, 8).map((f) => (
                <li key={f.id}>
                  {((f.amount_cents || 0) / 100).toFixed(2)} · <span className={f.status === "paid" ? "text-emerald-300" : "text-amber-300"}>{f.status}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </ExtSection>

      <ExtSection title="Support & Engagement" testid="ext-engagement">
        <DetailGrid>
          <DetailRow k="Lifetime sessions" v={`${detail.engagement?.lifetime_sessions ?? 0}`} />
          <DetailRow k="Last active" v={detail.engagement?.last_active_at
            ? new Date(detail.engagement.last_active_at).toLocaleString() : "—"} />
          <DetailRow k="Onboarding completed" v={detail.onboarding_completed
            ? <span className="text-emerald-300">yes</span>
            : <span className="text-amber-300">no</span>} />
        </DetailGrid>
        {(detail.feature_flags?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Feature flags / beta access</ExtSubTitle>
            <div className="flex flex-wrap gap-1.5">
              {detail.feature_flags.map((ff) => (
                <span key={ff} className="text-[10px] px-1.5 py-0.5 rounded-full border border-border">{ff}</span>
              ))}
            </div>
          </>
        )}
        {(detail.support_tickets?.length || 0) > 0 && (
          <>
            <ExtSubTitle>Support tickets · {detail.support_tickets.length}</ExtSubTitle>
            <ul className="text-xs space-y-0.5">
              {detail.support_tickets.slice(0, 8).map((t) => (
                <li key={t.id}>
                  <code>{t.ticket_id}</code>
                  {t.ticket_url && <a href={t.ticket_url} className="text-primary ml-2 underline" target="_blank" rel="noreferrer">open</a>}
                  {t.note && <span className="text-muted-foreground ml-2 italic">— {t.note}</span>}
                </li>
              ))}
            </ul>
          </>
        )}
      </ExtSection>

      <ExtSection title="Compliance & Legal" testid="ext-compliance">
        <DetailGrid>
          <DetailRow k="Date of birth" v={detail.compliance?.date_of_birth
            ? new Date(detail.compliance.date_of_birth).toLocaleDateString() : "—"} />
          <DetailRow k="Age verified" v={detail.compliance?.age_verified
            ? <span className="text-emerald-300">yes</span>
            : <span className="text-amber-300">no</span>} />
          <DetailRow k="ToS version" v={detail.compliance?.tos_version_accepted
            ? `${detail.compliance.tos_version_accepted} · ${detail.compliance.tos_accepted_at ? new Date(detail.compliance.tos_accepted_at).toLocaleDateString() : "—"}`
            : <span className="text-amber-300">not accepted</span>} />
          <DetailRow k="Marketing emails" v={detail.compliance?.marketing_email_consent ? "yes" : "no"} />
          <DetailRow k="Region / jurisdiction" v={
            <>
              {detail.compliance?.region || "—"}
              {detail.compliance?.jurisdiction_block && (
                <span className="ml-2 text-[10px] text-rose-300 px-1.5 py-0.5 rounded-full border border-rose-500/40">
                  blocked: {detail.compliance.jurisdiction_block}
                </span>
              )}
            </>
          } />
          <DetailRow k="Data deletion requested" v={detail.compliance?.data_deletion_requested_at
            ? new Date(detail.compliance.data_deletion_requested_at).toLocaleString() : "—"} />
          {detail.compliance?.data_deletion_completed_at && (
            <DetailRow k="Data deletion completed" v={
              <span className="text-rose-300">{new Date(detail.compliance.data_deletion_completed_at).toLocaleString()}</span>
            } />
          )}
        </DetailGrid>
        {Object.keys(detail.compliance?.privacy_consents || {}).length > 0 && (
          <>
            <ExtSubTitle>Privacy consents (GDPR/CCPA)</ExtSubTitle>
            <ul className="text-xs space-y-0.5">
              {Object.entries(detail.compliance.privacy_consents).map(([k, v]: any) => (
                <li key={k}>
                  <code>{k}</code>: {v === true ? <span className="text-emerald-300">granted</span> : v === false ? <span className="text-rose-300">denied</span> : String(v)}
                </li>
              ))}
            </ul>
          </>
        )}
      </ExtSection>
    </>
  );
}

function ExtSection({ title, testid, children }) {
  return (
    <section className="space-y-2" data-testid={testid}>
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</h4>
      <div className="rounded-lg border border-border p-3 space-y-3">{children}</div>
    </section>
  );
}

function ExtSubTitle({ children }) {
  return <p className="text-[11px] font-semibold uppercase tracking-wider text-foreground/60 pt-2 first:pt-0">{children}</p>;
}

function ExtEmpty({ children }) {
  return <p className="text-xs text-muted-foreground italic">{children}</p>;
}

function ExtTable({ head, children }) {
  return (
    <div className="rounded border border-border max-h-[280px] overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="bg-secondary/40 sticky top-0">
          <tr>
            {head.map((h) => (<th key={h} className="text-left px-2 py-1">{h}</th>))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function RoleBadge({ role }) {
  const palette: Record<string, string> = {
    commissioner: "border-amber-500/40 text-amber-300",
    co_commissioner: "border-sky-500/40 text-sky-300",
    manager: "border-border text-muted-foreground",
  };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${palette[role] || "border-border text-muted-foreground"}`}>
      {role?.replace(/_/g, " ")}
    </span>
  );
}
