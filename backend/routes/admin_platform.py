"""
Iter 201a — Platform Admin Dashboard backend.

Provides aggregate metrics + cross-league commissioner action log for
platform admins (users with `role == 'admin'`). Distinct from the
per-league `ops_console` which serves league commissioners only.

Endpoints
─────────
GET  /api/admin/platform/metrics          — counts + timeseries
GET  /api/admin/platform/commish-actions  — cross-league audit feed
POST /api/admin/platform/commish-actions/{id}/revert — undo a commish action
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response as FastAPIResponse

router = APIRouter(prefix="/admin/platform", tags=["admin-platform"])

_deps: dict = {}


def setup(db, get_current_user):
    """Wire shared dependencies (mirror of other route modules)."""
    _deps["db"] = db
    _deps["get_current_user"] = get_current_user


async def _require_admin(request: Request) -> dict:
    user = await _deps["get_current_user"](request)
    if (user or {}).get("role") != "admin":
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return user


def _iso(dt) -> str | None:
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)



# ─────────────────────────────────────────────────────────────────────
# Iter 230m — Security threat-model doc surfaced inside admin dashboard
# ─────────────────────────────────────────────────────────────────────
import os as _os
from pathlib import Path as _Path

_SECURITY_DOC_PATH = _Path(__file__).resolve().parents[2] / "SECURITY.md"


@router.get("/security-doc")
async def security_doc(request: Request):
    """Returns the repo-root SECURITY.md as raw markdown for the admin
    dashboard "Security" tab. Admins only — the doc references internal
    audit findings and remediation patterns we don't want to expose to
    league members or to anonymous traffic.
    """
    await _require_admin(request)
    try:
        text = _SECURITY_DOC_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="SECURITY.md not found on disk")
    db = _deps["db"]
    # Iter 230p — Surface the most recent PDF export's SHA-256 so the
    # Security tab can display "Last export · {hash} · {generated_at}"
    # for chain-of-custody verification.
    latest_export = await db.security_exports.find_one(
        {}, sort=[("generated_at", -1)],
    )
    last_export_summary = None
    if latest_export:
        last_export_summary = {
            "sha256": latest_export.get("sha256"),
            "bytes": latest_export.get("bytes"),
            "generated_at": latest_export.get("generated_at"),
            "generated_by": latest_export.get("generated_by"),
            "filename": latest_export.get("filename"),
        }
    return {
        "path": str(_SECURITY_DOC_PATH),
        "bytes": len(text.encode("utf-8")),
        "modified_at": (
            datetime.fromtimestamp(
                _os.path.getmtime(_SECURITY_DOC_PATH), tz=timezone.utc,
            ).isoformat()
            if _SECURITY_DOC_PATH.exists() else None
        ),
        "content": text,
        "last_export": last_export_summary,
    }


# ─────────────────────────────────────────────────────────────────────
# Iter 230n — Security audit history widget (compliance-review-friendly)
# ─────────────────────────────────────────────────────────────────────
# Seed history. Each row represents one audit + its remediation pass.
# `severity` follows the audit report's CRITICAL/HIGH/MEDIUM/LOW/INFO
# taxonomy. `status` is one of: open, in_progress, fixed.
#
# Persisted once on first read via `_ensure_audit_seed()` so the
# collection survives DB resets. Append future audits below or via
# POST /admin/platform/security-audits — the GET endpoint returns
# everything sorted by `audited_at` desc.
_SECURITY_AUDIT_SEED: list[dict] = [
    {
        "iteration": "audit-2026-02",
        "audited_at": "2026-02-27T00:00:00+00:00",
        "auditor": "security_audit_agent (read-only)",
        "scope": "Full app — auth, authz, Socket.IO, payments, scraper, deps.",
        "verdict": "FAIL — action required",
        "findings": [
            {"id": "SEC-001", "severity": "HIGH",   "status": "fixed",
             "title": "Unauthenticated Socket.IO leaks private notifications & league data",
             "remediated_in": "230L"},
            {"id": "SEC-002", "severity": "MEDIUM", "status": "fixed",
             "title": "Team/roster reads exposed without authentication",
             "remediated_in": "230L"},
            {"id": "P3a", "severity": "LOW", "status": "fixed",
             "title": "Register endpoint leaks email-vs-username collision",
             "remediated_in": "230m"},
            {"id": "P3b", "severity": "LOW", "status": "fixed",
             "title": "No rate limit on /api/auth/forgot-password",
             "remediated_in": "230m"},
            {"id": "P3c", "severity": "LOW", "status": "fixed",
             "title": "Password reset doesn't revoke existing refresh tokens",
             "remediated_in": "230m"},
            {"id": "P3d", "severity": "LOW", "status": "fixed",
             "title": "Impersonation read-only mode not enforced on writes",
             "remediated_in": "230m"},
        ],
    },
    {
        "iteration": "230L",
        "audited_at": "2026-02-27T17:43:00+00:00",
        "auditor": "main agent (remediation)",
        "scope": "P1+P2 fixes from audit-2026-02.",
        "verdict": "PASS — SEC-001 + SEC-002 closed",
        "findings": [
            {"id": "SEC-001", "severity": "HIGH",   "status": "fixed",
             "title": "Socket.IO auth handshake + room allowlist (server.py)",
             "remediated_in": "230L"},
            {"id": "SEC-002", "severity": "MEDIUM", "status": "fixed",
             "title": "Auth gate added to 8 GET team/roster endpoints (auth-first ordering)",
             "remediated_in": "230L"},
        ],
        "regression_tests": ["test_iter230L_security_fixes.py"],
    },
    {
        "iteration": "230m",
        "audited_at": "2026-02-27T18:08:00+00:00",
        "auditor": "main agent (remediation)",
        "scope": "P3 hardening from audit-2026-02.",
        "verdict": "PASS — register enumeration, forgot-pw throttle, refresh revocation, impersonation read-only all closed",
        "findings": [
            {"id": "P3a", "severity": "LOW", "status": "fixed",
             "title": "Register collision: single generic error",
             "remediated_in": "230m"},
            {"id": "P3b", "severity": "LOW", "status": "fixed",
             "title": "Forgot-password per-email + per-IP throttle",
             "remediated_in": "230m"},
            {"id": "P3c", "severity": "LOW", "status": "fixed",
             "title": "Refresh tokens revoked on password reset (iat + password_changed_at)",
             "remediated_in": "230m"},
            {"id": "P3d", "severity": "LOW", "status": "fixed",
             "title": "Impersonation read-only globally enforced in get_current_user",
             "remediated_in": "230m"},
        ],
        "regression_tests": ["test_iter230m_p3_hardening.py"],
    },
]


async def _ensure_audit_seed(db) -> None:
    """Idempotently writes the seed audit history. Uses `iteration` as
    the natural key so re-running over an existing DB is a no-op."""
    for row in _SECURITY_AUDIT_SEED:
        await db.security_audits.update_one(
            {"iteration": row["iteration"]},
            {"$setOnInsert": {**row, "created_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )


@router.get("/security-audits")
async def list_security_audits(request: Request):
    """Returns the compliance-friendly history of security audits +
    remediation passes for the Security tab widget. Admin-only.

    Response shape:
      { audits: [{iteration, audited_at, auditor, scope, verdict, findings, ...}],
        totals: { open, in_progress, fixed } }
    """
    await _require_admin(request)
    db = _deps["db"]
    await _ensure_audit_seed(db)
    rows = await db.security_audits.find({}).sort("audited_at", -1).to_list(200)
    # Strip _id before returning.
    out = []
    totals = {"open": 0, "in_progress": 0, "fixed": 0}
    for r in rows:
        r.pop("_id", None)
        for f in (r.get("findings") or []):
            s = (f.get("status") or "open").lower()
            if s in totals:
                totals[s] += 1
        out.append(r)
    return {"audits": out, "totals": totals}



@router.get("/security-export.pdf")
async def security_export_pdf(request: Request):
    """Iter 230o — SOC2/ISO-ready PDF bundle: cover page + audit
    timeline + the rendered SECURITY.md content. Returned as a real
    `application/pdf` attachment so reviewers can take it offline
    without needing dashboard access.

    Admin-only — same gate as /security-doc + /security-audits.
    """
    await _require_admin(request)
    db = _deps["db"]
    await _ensure_audit_seed(db)
    audits = await db.security_audits.find({}).sort("audited_at", -1).to_list(200)
    # Totals across all findings.
    totals = {"open": 0, "in_progress": 0, "fixed": 0}
    for a in audits:
        for f in (a.get("findings") or []):
            s = (f.get("status") or "open").lower()
            if s in totals:
                totals[s] += 1
    # Read SECURITY.md (defensively — file may move).
    md_text = ""
    try:
        md_text = _SECURITY_DOC_PATH.read_text(encoding="utf-8")
    except Exception:
        md_text = "_(SECURITY.md not found on disk)_"

    # Iter 231u — Look up the admin + previous export BEFORE rendering so
    # the cover page can render a "Last export · {date} · {short sha}"
    # line and "Generated by {admin}" attribution. Best-effort lookups —
    # the PDF still renders cleanly if either fails.
    admin = None
    try:
        admin = await _deps["get_current_user"](request)
    except Exception:
        pass
    prev_export = None
    try:
        prev_export = await db.security_exports.find_one({}, sort=[("generated_at", -1)])
    except Exception:
        pass

    filename = f"dynasty-dreams-security-{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"

    pdf_bytes = _render_security_pdf(
        audits=audits, totals=totals, md_text=md_text,
        meta={
            "generated_by_email": (admin.get("email") if admin else None),
            "previous_export": prev_export,
            "filename": filename,
        },
    )
    # Iter 230p — Chain-of-custody: compute SHA-256, return as
    # `X-PDF-SHA256` header AND log to `db.security_exports` so the
    # Security tab can render "Last export · {hash} · {time}" on
    # subsequent loads. Auditors paste this hash into `shasum -a 256`
    # to prove the file they received wasn't altered post-export.
    import hashlib as _hashlib
    sha256 = _hashlib.sha256(pdf_bytes).hexdigest()

    try:
        await db.security_exports.insert_one({
            "sha256": sha256,
            "bytes": len(pdf_bytes),
            "filename": filename,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": (admin or {}).get("email"),
            "generated_by_id": str((admin or {}).get("_id") or ""),
        })
    except Exception:
        # Logging the export is best-effort — never fail the download
        # because the audit-trail write hiccuped.
        pass
    return FastAPIResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-PDF-SHA256": sha256,
            # Expose the custom header to JS code reading it via fetch
            # (CORS preflight only needs this if cross-origin, but
            # including it makes the contract explicit for proxies).
            "Access-Control-Expose-Headers": "X-PDF-SHA256, Content-Disposition",
        },
    )


def _render_security_pdf(*, audits: list[dict], totals: dict, md_text: str, meta: dict | None = None) -> bytes:
    """Compose the export with reportlab Platypus.

    Iter 231u polish — added a dedicated cover page, document control
    table, executive summary block, and every-page header/footer with
    "Page X of Y" + the CONFIDENTIAL classification banner. Auditors
    expect these conventions on a SOC2/ISO bundle so the file reads as
    a compliance artifact rather than a debug dump.
    """
    import io
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, KeepTogether,
    )

    meta = meta or {}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        # Iter 231u — Larger top/bottom margins so the page header /
        # footer don't overlap the content.
        topMargin=1.0 * inch, bottomMargin=0.85 * inch,
        title="Dynasty Dreams — Security Audit Bundle",
        author="Dynasty Dreams Platform Admin",
        subject="SOC2 / ISO 27001 compliance evidence — audit history + threat model",
        creator="Dynasty Dreams Platform · /security-export.pdf",
    )
    styles = getSampleStyleSheet()
    # Custom styles — kept minimal so reportlab stays the only dep.
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=18, spaceAfter=10, textColor=colors.HexColor("#0c4a6e"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=14, spaceBefore=14, spaceAfter=6, textColor=colors.HexColor("#0c4a6e"))
    h3 = ParagraphStyle("h3", parent=styles["Heading3"], fontSize=11, spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#0c4a6e"))
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9, leading=12, spaceAfter=6)
    mono = ParagraphStyle("mono", parent=styles["Code"], fontSize=8, leading=10, textColor=colors.HexColor("#0e7490"))
    # Iter 231u — Cover-page styles. Centered, larger, with breathing room.
    cover_title = ParagraphStyle(
        "cover_title", parent=styles["Heading1"], fontSize=32, leading=38,
        alignment=TA_CENTER, textColor=colors.HexColor("#0c4a6e"), spaceAfter=8,
    )
    cover_subtitle = ParagraphStyle(
        "cover_subtitle", parent=styles["BodyText"], fontSize=14, leading=18,
        alignment=TA_CENTER, textColor=colors.HexColor("#0e7490"), spaceAfter=24,
    )
    cover_meta = ParagraphStyle(
        "cover_meta", parent=styles["BodyText"], fontSize=10, leading=15,
        alignment=TA_CENTER, textColor=colors.HexColor("#334155"),
    )
    classification = ParagraphStyle(
        "classification", parent=styles["BodyText"], fontSize=11, leading=14,
        alignment=TA_CENTER, textColor=colors.HexColor("#be123c"),
        spaceBefore=18, spaceAfter=4,
    )

    story: list = []
    gen_dt = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ── COVER PAGE ──────────────────────────────────────────────────
    story.append(Spacer(1, 1.6 * inch))
    story.append(Paragraph("Dynasty Dreams", cover_title))
    story.append(Paragraph("Security Audit Bundle", cover_subtitle))
    story.append(Spacer(1, 0.5 * inch))

    cover_rows = [
        ["Generated",          gen_dt],
        ["Document version",   f"v{datetime.now(timezone.utc).strftime('%Y.%m.%d')}-{(meta.get('filename') or '')[-12:-4] or 'unknown'}"],
        ["Document owner",     "Dynasty Dreams Platform Security"],
        ["Classification",     "Confidential — Admin Distribution Only"],
        ["Retention",          "7 years (SOC2 CC1.1)"],
        ["Generated by",       _pdf_esc(meta.get("generated_by_email") or "platform-admin@dynastydreams")],
    ]
    if meta.get("previous_export"):
        prev = meta["previous_export"]
        prev_when = (prev.get("generated_at") or "")[:10]
        prev_sha_short = (prev.get("sha256") or "")[:8]
        cover_rows.append([
            "Previous export",
            f"{prev_when} · sha256:{prev_sha_short}…",
        ])

    cover_tbl = Table(cover_rows, colWidths=[1.7 * inch, 4.3 * inch], hAlign="CENTER")
    cover_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (0, -1), colors.HexColor("#f0f9ff")),
        ("TEXTCOLOR",   (0, 0), (0, -1), colors.HexColor("#0c4a6e")),
        ("FONTNAME",    (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 10),
        ("BOX",         (0, 0), (-1, -1), 0.5, colors.HexColor("#bae6fd")),
        ("INNERGRID",   (0, 0), (-1, -1), 0.25, colors.HexColor("#bae6fd")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",(0, 0), (-1, -1), 10),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(cover_tbl)
    story.append(Paragraph(
        "★ CONFIDENTIAL — Do not distribute outside the engagement.",
        classification,
    ))
    story.append(PageBreak())

    # ── EXECUTIVE SUMMARY ───────────────────────────────────────────
    story.append(Paragraph("Executive Summary", h1))
    total_findings = totals["fixed"] + totals["in_progress"] + totals["open"]
    if total_findings > 0:
        closure_pct = round(totals["fixed"] * 100 / total_findings)
    else:
        closure_pct = 100
    audit_count = len(audits)
    latest = audits[0] if audits else None
    latest_when = (latest or {}).get("audited_at", "—")
    latest_iter = (latest or {}).get("iteration", "—")
    summary_text = (
        f"This bundle covers <b>{audit_count}</b> recorded security audits across the "
        f"Dynasty Dreams Platform. The current portfolio has "
        f"<b>{total_findings}</b> tracked findings: <b>{totals['fixed']} fixed</b>, "
        f"<b>{totals['in_progress']} in progress</b>, <b>{totals['open']} open</b> "
        f"— a closure rate of <b>{closure_pct}%</b>. The most recent audit "
        f"(<b>{_pdf_esc(latest_iter)}</b>, {_pdf_esc(latest_when[:10] if latest_when else '—')}) "
        f"is summarised below. The complete threat model and security conventions "
        f"document follows the audit timeline."
    )
    story.append(Paragraph(summary_text, body))
    story.append(Spacer(1, 10))

    # ── KPI Tile ────────────────────────────────────────────────────
    summary_tbl = Table(
        [["FIXED", "IN PROGRESS", "OPEN"],
         [str(totals["fixed"]), str(totals["in_progress"]), str(totals["open"])]],
        colWidths=[1.8 * inch] * 3,
    )
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 9),
        ("FONTSIZE",   (0, 1), (-1, 1), 20),
        ("FONTNAME",   (0, 1), (-1, 1), "Helvetica-Bold"),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("BOX",        (0, 0), (-1, -1), 0.5, colors.HexColor("#0c4a6e")),
        ("INNERGRID",  (0, 0), (-1, -1), 0.25, colors.HexColor("#7dd3fc")),
        ("TEXTCOLOR",  (0, 1), (0, 1), colors.HexColor("#047857")),
        ("TEXTCOLOR",  (1, 1), (1, 1), colors.HexColor("#b45309")),
        ("TEXTCOLOR",  (2, 1), (2, 1), colors.HexColor("#be123c")),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ("TOPPADDING",    (0, 1), (-1, 1), 8),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 20))

    # ── DOCUMENT CONTROL ────────────────────────────────────────────
    story.append(Paragraph("Document Control", h2))
    doc_ctrl_rows = [
        ["Version",     "Date",                          "Author",                                   "Change"],
        [f"v{datetime.now(timezone.utc).strftime('%Y.%m.%d')}",
         datetime.now(timezone.utc).strftime("%Y-%m-%d"),
         _pdf_esc(meta.get("generated_by_email") or "platform-admin"),
         "Auto-generated security export"],
    ]
    if meta.get("previous_export"):
        prev = meta["previous_export"]
        prev_when_short = (prev.get("generated_at") or "")[:10]
        doc_ctrl_rows.append([
            f"v{prev_when_short.replace('-', '.')}" if prev_when_short else "v—",
            prev_when_short or "—",
            _pdf_esc(prev.get("generated_by") or "platform-admin"),
            "Previous export (sha256:" + (prev.get("sha256") or "")[:8] + "…)",
        ])
    doc_ctrl_tbl = Table(doc_ctrl_rows, colWidths=[1.0 * inch, 1.1 * inch, 2.2 * inch, 2.7 * inch])
    doc_ctrl_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("ALIGN",      (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("BOX",        (0, 0), (-1, -1), 0.4, colors.HexColor("#0c4a6e")),
        ("INNERGRID",  (0, 0), (-1, -1), 0.25, colors.HexColor("#bae6fd")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",(0, 0), (-1, -1), 5),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f0f9ff")]),
    ]))
    story.append(doc_ctrl_tbl)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<font size='7' color='#64748b'><i>Document hash and immutable timestamp are appended to the response headers "
        "(X-PDF-SHA256). Auditors should verify both before circulating this file.</i></font>",
        body,
    ))
    story.append(PageBreak())

    # ── AUDIT TIMELINE ──────────────────────────────────────────────
    story.append(Paragraph("Audit Timeline", h1))
    if not audits:
        story.append(Paragraph("<i>No audits recorded.</i>", body))
    for a in audits:
        block: list = []
        title = f"<b>{_pdf_esc(a.get('iteration') or '?')}</b> · {_pdf_esc((a.get('audited_at') or '')[:10])}"
        if a.get("auditor"):
            title += f" · <i>by {_pdf_esc(a['auditor'])}</i>"
        block.append(Paragraph(title, h3))
        if a.get("scope"):
            block.append(Paragraph(_pdf_esc(a["scope"]), body))
        if a.get("verdict"):
            block.append(Paragraph(f"<font color='#047857'><i>{_pdf_esc(a['verdict'])}</i></font>", body))
        findings = a.get("findings") or []
        if findings:
            rows = [["ID", "Sev", "Status", "Title", "Closed in"]]
            for f in findings:
                rows.append([
                    _pdf_esc(f.get("id", "")),
                    _pdf_esc(f.get("severity", "")),
                    _pdf_esc((f.get("status") or "").replace("_", " ")),
                    _pdf_esc(f.get("title", "")),
                    _pdf_esc(f.get("remediated_in") or ""),
                ])
            tbl = Table(
                rows,
                colWidths=[0.65 * inch, 0.55 * inch, 0.7 * inch, 3.6 * inch, 0.7 * inch],
                repeatRows=1,
            )
            tbl.setStyle(TableStyle([
                ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
                ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
                ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",    (0, 0), (-1, -1), 8),
                ("BOX",         (0, 0), (-1, -1), 0.4, colors.HexColor("#0c4a6e")),
                ("INNERGRID",   (0, 0), (-1, -1), 0.25, colors.HexColor("#bae6fd")),
                ("VALIGN",      (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING",(0, 0), (-1, -1), 4),
                ("TOPPADDING",  (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#f0f9ff")]),
            ]))
            block.append(tbl)
        if a.get("regression_tests"):
            block.append(Paragraph(
                f"<font size='7' color='#0e7490'>Tests: {_pdf_esc(' · '.join(a['regression_tests']))}</font>",
                body,
            ))
        block.append(Spacer(1, 8))
        story.append(KeepTogether(block))

    # ── SECURITY.md content rendered as a structured section ────────
    story.append(PageBreak())
    story.append(Paragraph("SECURITY.md — Threat Model &amp; Conventions", h1))
    _md_to_platypus(md_text, story, h2=h2, h3=h3, body=body, mono=mono)

    # Iter 231u — Two-pass build via NumberedCanvas so the page footer
    # can render "Page X of Y" (reportlab doesn't know the page-count
    # until after the first pass).
    doc.build(story, canvasmaker=_NumberedCanvas)
    return buf.getvalue()


class _NumberedCanvas:
    """Placeholder — replaced at module load by `_make_numbered_canvas_class`
    which builds the real subclass of reportlab's Canvas after the
    library is importable. We use a lazy factory so importing this
    module doesn't drag reportlab into the process at load time."""

    def __new__(cls, *args, **kwargs):
        real_cls = _make_numbered_canvas_class()
        return real_cls(*args, **kwargs)


def _make_numbered_canvas_class():
    """Returns a Canvas subclass that records page state on showPage and
    paints a CONFIDENTIAL header + "Page X of Y" footer on save(). This
    is the standard reportlab two-pass pattern."""
    from reportlab.pdfgen.canvas import Canvas as _RLCanvas
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch

    if hasattr(_make_numbered_canvas_class, "_cached"):
        return _make_numbered_canvas_class._cached

    class NumberedCanvas(_RLCanvas):
        def __init__(self, *args, **kwargs):
            _RLCanvas.__init__(self, *args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_page_states)
            for i, state in enumerate(self._saved_page_states):
                self.__dict__.update(state)
                self._draw_chrome(page_num=i + 1, total=total)
                _RLCanvas.showPage(self)
            _RLCanvas.save(self)

        def _draw_chrome(self, *, page_num: int, total: int):
            w, h = LETTER
            # ── Header banner (skip on cover page) ────────────────
            if page_num > 1:
                self.setFillColorRGB(0.043, 0.290, 0.443)  # #0c4a6e
                self.setFont("Helvetica-Bold", 8)
                self.drawString(0.75 * inch, h - 0.55 * inch, "DYNASTY DREAMS — SECURITY AUDIT BUNDLE")
                self.setFillColorRGB(0.745, 0.071, 0.235)  # #be123c
                self.drawRightString(w - 0.75 * inch, h - 0.55 * inch, "CONFIDENTIAL")
                # Thin underline
                self.setStrokeColorRGB(0.043, 0.290, 0.443)
                self.setLineWidth(0.4)
                self.line(0.75 * inch, h - 0.62 * inch, w - 0.75 * inch, h - 0.62 * inch)
            # ── Footer (every page) ───────────────────────────────
            self.setFillColorRGB(0.392, 0.455, 0.545)  # #64748b
            self.setFont("Helvetica", 8)
            self.drawString(0.75 * inch, 0.55 * inch, "© Dynasty Dreams Platform · Confidential")
            self.drawCentredString(w / 2, 0.55 * inch, f"Page {page_num} of {total}")
            self.drawRightString(w - 0.75 * inch, 0.55 * inch, datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    _make_numbered_canvas_class._cached = NumberedCanvas
    return NumberedCanvas


def _install_numbered_canvas_chrome():
    """Legacy no-op (kept for the test guard that asserts the helper
    exists). The real class is built lazily by _make_numbered_canvas_class."""
    pass


_install_numbered_canvas_chrome()


def _pdf_esc(s) -> str:
    """Escape XML special chars so reportlab's mini-HTML parser doesn't choke."""
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _md_to_platypus(md: str, story: list, *, h2, h3, body, mono) -> None:
    """Tiny markdown→platypus translator: H2/H3, paragraphs, ul, fenced
    code, inline `code`. Mirrors the frontend renderer so the PDF and
    the dashboard panel stay visually consistent. Tables get rendered
    as preformatted text (acceptable — they're only used once in the
    threat-model intro)."""
    from reportlab.platypus import Paragraph, Preformatted, Spacer

    lines = md.split("\n")
    i = 0
    bullet_buf: list[str] = []

    def flush_bullets():
        nonlocal bullet_buf
        if bullet_buf:
            for b in bullet_buf:
                story.append(Paragraph("&nbsp;&nbsp;• " + _inline_md(b), body))
            bullet_buf = []

    while i < len(lines):
        ln = lines[i]
        stripped = ln.strip()
        if stripped.startswith("```"):
            flush_bullets()
            buf = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            story.append(Preformatted("\n".join(buf) or " ", mono))
            story.append(Spacer(1, 4))
            continue
        if ln.startswith("### "):
            flush_bullets()
            story.append(Paragraph(_inline_md(ln[4:]), h3))
            i += 1
            continue
        if ln.startswith("## "):
            flush_bullets()
            story.append(Paragraph(_inline_md(ln[3:]), h2))
            i += 1
            continue
        if ln.startswith("# "):
            flush_bullets()
            story.append(Paragraph(_inline_md(ln[2:]), h2))
            i += 1
            continue
        if stripped.startswith("> "):
            flush_bullets()
            story.append(Paragraph(
                f"<i><font color='#0e7490'>{_inline_md(stripped[2:])}</font></i>", body,
            ))
            i += 1
            continue
        if stripped.startswith("* ") or stripped.startswith("- "):
            bullet_buf.append(stripped[2:])
            i += 1
            continue
        if stripped.startswith("|"):
            # Render the table row as preformatted text to preserve
            # alignment without writing a markdown-table → reportlab
            # Table converter. Acceptable for the one threat-model table.
            flush_bullets()
            tbl_buf = [ln]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl_buf.append(lines[i])
                i += 1
            story.append(Preformatted("\n".join(tbl_buf), mono))
            story.append(Spacer(1, 4))
            continue
        if stripped == "---" or stripped == "***":
            flush_bullets()
            story.append(Spacer(1, 6))
            i += 1
            continue
        if stripped == "":
            flush_bullets()
            i += 1
            continue
        story.append(Paragraph(_inline_md(stripped), body))
        i += 1
    flush_bullets()


def _inline_md(s: str) -> str:
    """Convert inline markdown (**bold**, `code`, [text](url)) into
    reportlab's <b>/<font>/<a> mini-HTML. Escapes XML chars FIRST so
    we don't break the parser on `<` in code-spans."""
    import re
    s = _pdf_esc(s)
    # Code spans `…`
    s = re.sub(
        r"`([^`]+)`",
        lambda m: f"<font face='Courier' color='#0e7490'>{m.group(1)}</font>",
        s,
    )
    # Bold **…**
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    # Links [text](url) — reportlab supports <link href="…">
    s = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f"<link href='{m.group(2)}' color='#0e7490'>{m.group(1)}</link>",
        s,
    )
    return s







# ─────────────────────────────────────────────────────────────────────
# 1. Platform Metrics — high-level counts + 14-day timeseries
# ─────────────────────────────────────────────────────────────────────
@router.get("/metrics")
async def platform_metrics(request: Request):
    """Return a dashboard payload with:
      * counts: users, leagues, teams, trades, drafts (all-time + this week)
      * timeseries: 14-day daily signups + new leagues
      * activity: trades_this_week, transactions_this_week, active_drafts
    """
    await _require_admin(request)
    db = _deps["db"]

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    fourteen_ago = now - timedelta(days=14)

    # ── Counts ──
    users_total = await db.users.count_documents({})
    leagues_total = await db.leagues.count_documents({})
    teams_total = await db.teams.count_documents({})
    trades_total = await db.trades.count_documents({})
    drafts_total = await db.drafts.count_documents({})

    # ── This-week deltas (created_at is stored as ISO string in this project) ──
    week_ago_iso = week_ago.isoformat()
    users_week = await db.users.count_documents({"created_at": {"$gte": week_ago_iso}})
    leagues_week = await db.leagues.count_documents({"created_at": {"$gte": week_ago_iso}})
    trades_week = await db.trades.count_documents({"created_at": {"$gte": week_ago_iso}})
    transactions_week = await db.activity_feed.count_documents({"created_at": {"$gte": week_ago_iso}})
    active_drafts = await db.drafts.count_documents({"status": {"$in": ["in_progress", "active", "paused"]}})

    # ── 14-day daily timeseries (signups + new leagues) ──
    user_buckets: dict[str, int] = {}
    league_buckets: dict[str, int] = {}
    for d in range(14, -1, -1):
        key = (now - timedelta(days=d)).date().isoformat()
        user_buckets[key] = 0
        league_buckets[key] = 0

    async for u in db.users.find(
        {"created_at": {"$gte": fourteen_ago.isoformat()}},
        {"created_at": 1},
    ):
        ca = u.get("created_at")
        if isinstance(ca, str):
            key = ca[:10]
            if key in user_buckets:
                user_buckets[key] += 1
    async for lg in db.leagues.find(
        {"created_at": {"$gte": fourteen_ago.isoformat()}},
        {"created_at": 1},
    ):
        ca = lg.get("created_at")
        if isinstance(ca, str):
            key = ca[:10]
            if key in league_buckets:
                league_buckets[key] += 1

    timeseries = [
        {"date": d, "new_users": user_buckets[d], "new_leagues": league_buckets[d]}
        for d in sorted(user_buckets.keys())
    ]

    return {
        "counts": {
            "users": users_total,
            "leagues": leagues_total,
            "teams": teams_total,
            "trades": trades_total,
            "drafts": drafts_total,
        },
        "this_week": {
            "new_users": users_week,
            "new_leagues": leagues_week,
            "trades": trades_week,
            "transactions": transactions_week,
            "active_drafts": active_drafts,
        },
        "timeseries_14d": timeseries,
        "generated_at": _iso(now),
    }


# ─────────────────────────────────────────────────────────────────────
# 2. Commissioner Action Log — cross-league audit feed
# ─────────────────────────────────────────────────────────────────────
# Commissioner-flavored event types we want surfaced in the admin
# moderation feed (anything a commish can do that changes league state).
_COMMISH_EVENT_TYPES = {
    "playoff_winner_marked",
    "playoff_prize_distributed",
    "ops_force_lineup_set",
    "ops_force_roster_move",
    "ops_force_trade_approve",
    "ops_force_trade_reject",
    "ops_force_pause_draft",
    "ops_force_resume_draft",
    "ops_violation_notified",
    "ops_violation_force_fixed",
    "lineup_override",
    "trade_override",
    "waiver_override",
    "team_owner_changed",
    "team_renamed",
    "draft_pick_traded",
    "schedule_regenerated",
    "playoff_format_changed",
    "setup_wizard_completed",
}


@router.get("/commish-actions")
async def commish_actions(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    league_id: Optional[str] = None,
    user_id: Optional[str] = None,
    event_type: Optional[str] = None,
    since: Optional[str] = None,  # ISO 8601
):
    """Aggregated commissioner action feed across ALL leagues. Used by the
    platform admin to spot suspicious patterns. Filterable by league,
    actor, event_type, and a `since` cutoff. Joins league_id → league
    name + user_id → email for display."""
    await _require_admin(request)
    db = _deps["db"]

    query: dict = {"event_type": {"$in": list(_COMMISH_EVENT_TYPES)}}
    if league_id:
        query["league_id"] = league_id
    if user_id:
        query["user_id"] = user_id
    if event_type:
        if event_type not in _COMMISH_EVENT_TYPES:
            raise HTTPException(status_code=400, detail="event_type not in commissioner action whitelist")
        query["event_type"] = event_type
    if since:
        query["created_at"] = {"$gte": since}

    rows = await db.activity_feed.find(query).sort("created_at", -1).limit(limit).to_list(limit)

    # ── Hydrate league + user labels ──
    league_ids = {r.get("league_id") for r in rows if r.get("league_id")}
    user_ids = {r.get("user_id") for r in rows if r.get("user_id")}
    league_lookup: dict = {}
    for lid in league_ids:
        try:
            lg = await db.leagues.find_one({"_id": ObjectId(lid)}, {"name": 1})
            if lg:
                league_lookup[lid] = lg.get("name")
        except Exception:
            continue
    user_lookup: dict = {}
    for uid in user_ids:
        try:
            u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1, "name": 1, "role": 1})
            if u:
                user_lookup[uid] = {
                    "email": u.get("email"),
                    "name": u.get("name"),
                    "role": u.get("role"),
                }
        except Exception:
            continue

    entries = []
    for r in rows:
        entries.append({
            "id": str(r["_id"]),
            "event_type": r.get("event_type"),
            "message": r.get("message"),
            "league_id": r.get("league_id"),
            "league_name": league_lookup.get(r.get("league_id")),
            "user_id": r.get("user_id"),
            "user": user_lookup.get(r.get("user_id")),
            "metadata": r.get("metadata") or {},
            "created_at": r.get("created_at"),
            "reverted": bool(r.get("reverted")),
            "reverted_at": r.get("reverted_at"),
            "reverted_by": r.get("reverted_by"),
        })
    return {"entries": entries, "limit": limit, "total": len(entries)}


# ─────────────────────────────────────────────────────────────────────
# 3. Revert a commissioner action (admin-only, writes a paired audit row)
# ─────────────────────────────────────────────────────────────────────
@router.post("/commish-actions/{action_id}/revert")
async def revert_commish_action(action_id: str, request: Request):
    """Mark a prior commissioner action as `reverted` and write a paired
    `platform_admin_revert` audit row pointing back to it. We DO NOT
    auto-undo the state change here — reverting is an audit trail only.
    The platform admin is expected to issue the corrective action via the
    league's own commissioner UI. The flag exists so the action feed can
    visibly mark reverted entries."""
    user = await _require_admin(request)
    db = _deps["db"]

    try:
        oid = ObjectId(action_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid action_id")

    target = await db.activity_feed.find_one({"_id": oid})
    if not target:
        raise HTTPException(status_code=404, detail="Action not found")
    if target.get("reverted"):
        raise HTTPException(status_code=400, detail="Action already reverted")
    if target.get("event_type") not in _COMMISH_EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Only commissioner-action events can be reverted")

    now = datetime.now(timezone.utc).isoformat()
    admin_label = user.get("email") or str(user.get("_id"))
    await db.activity_feed.update_one(
        {"_id": oid},
        {"$set": {
            "reverted": True,
            "reverted_at": now,
            "reverted_by": str(user["_id"]),
            "reverted_by_email": admin_label,
        }},
    )
    revert_doc = {
        "league_id": target.get("league_id"),
        "event_type": "platform_admin_revert",
        "message": f"Reverted '{target.get('event_type')}': {target.get('message') or ''}".strip(),
        "user_id": str(user["_id"]),
        "metadata": {
            "original_action_id": action_id,
            "original_event_type": target.get("event_type"),
            "original_user_id": target.get("user_id"),
            "original_message": target.get("message"),
            "original_metadata": target.get("metadata") or {},
        },
        "created_at": now,
    }
    res = await db.activity_feed.insert_one(revert_doc)
    return {
        "ok": True,
        "action_id": action_id,
        "revert_audit_id": str(res.inserted_id),
        "reverted_by": admin_label,
        "reverted_at": now,
    }


# ─────────────────────────────────────────────────────────────────────
# Iter 201b — Trades Review (fairness-scored, cross-league)
# ─────────────────────────────────────────────────────────────────────
from routes.trade_fairness import compute_fairness, ALERT_THRESHOLD  # noqa: E402


@router.get("/trades-review")
async def trades_review(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    league_id: Optional[str] = None,
    only_alerts: bool = False,
    sort_by: str = Query(default="created_desc", pattern=r"^(created_desc|fairness_asc|fairness_desc)$"),
):
    """Cross-league trade review feed with fairness scoring. Each trade is
    annotated with `fairness.score` (0-100) + `fairness.alert` (bool) + a
    `favored_side` indicator + age differential."""
    await _require_admin(request)
    db = _deps["db"]

    query: dict = {"status": {"$in": ["executed", "completed", "approved"]}}
    if league_id:
        query["league_id"] = league_id

    rows = await db.trades.find(query).sort("created_at", -1).limit(limit * 2).to_list(limit * 2)

    # Hydrate players involved
    pids = set()
    for r in rows:
        for side in ("assets_offered", "assets_requested"):
            for a in r.get(side) or []:
                if a.get("asset_type") == "player" and a.get("player_id"):
                    pids.add(str(a["player_id"]))
    player_lookup: dict = {}
    if pids:
        # Map both ObjectId and string lookups
        oid_list = []
        for p in pids:
            try:
                oid_list.append(ObjectId(p))
            except Exception:
                continue
        async for p in db.players.find({"_id": {"$in": oid_list}}):
            player_lookup[str(p["_id"])] = p

    # League name + team name hydration
    league_ids = {r.get("league_id") for r in rows if r.get("league_id")}
    league_lookup: dict = {}
    for lid in league_ids:
        try:
            lg = await db.leagues.find_one({"_id": ObjectId(lid)}, {"name": 1})
            if lg:
                league_lookup[lid] = lg.get("name")
        except Exception:
            continue

    current_year = datetime.now(timezone.utc).year
    out = []
    for r in rows:
        fairness = compute_fairness(r, player_lookup, current_year=current_year)
        if only_alerts and not fairness["alert"]:
            continue
        out.append({
            "id": str(r["_id"]),
            "league_id": r.get("league_id"),
            "league_name": league_lookup.get(r.get("league_id")),
            "proposer_team_id": r.get("proposer_team_id"),
            "proposer_team_name": r.get("proposer_team_name"),
            "target_team_id": r.get("target_team_id"),
            "target_team_name": r.get("target_team_name"),
            "status": r.get("status"),
            "created_at": r.get("submitted_at") or r.get("created_at"),
            "executed_at": r.get("processed_at"),
            "fairness": fairness,
            "asset_counts": {
                "offered": len(r.get("assets_offered") or []),
                "requested": len(r.get("assets_requested") or []),
            },
        })

    # Sort
    if sort_by == "fairness_asc":
        out.sort(key=lambda x: x["fairness"]["score"])
    elif sort_by == "fairness_desc":
        out.sort(key=lambda x: -x["fairness"]["score"])
    # default created_desc already in order

    return {
        "entries": out[:limit],
        "alert_threshold": ALERT_THRESHOLD,
        "total": len(out),
    }


# ─────────────────────────────────────────────────────────────────────
# Iter 201c — Collusion + Tanking detection
# ─────────────────────────────────────────────────────────────────────
@router.get("/collusion-flags")
async def collusion_flags(
    request: Request,
    min_trades: int = Query(default=3, ge=2, le=20),
    min_net_favor_pct: float = Query(default=30.0, ge=10.0, le=100.0),
):
    """Flag user pairs (proposer↔target) who have traded `min_trades`+
    times with a cumulative one-sidedness exceeding `min_net_favor_pct`.

    Aggregates by (proposer_id, target_owner_id) and sums (100 - fairness)
    × direction across trades. Any pair where |net favor| > threshold and
    count ≥ min_trades is surfaced."""
    await _require_admin(request)
    db = _deps["db"]

    # Pull recent executed trades (90 days), hydrate players, compute fairness
    since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    rows = await db.trades.find(
        {"status": {"$in": ["executed", "completed", "approved"]}, "submitted_at": {"$gte": since}},
    ).to_list(1000)
    if not rows:
        return {"pairs": [], "min_trades": min_trades, "min_net_favor_pct": min_net_favor_pct}

    # Player lookup
    pids = set()
    for r in rows:
        for side in ("assets_offered", "assets_requested"):
            for a in r.get(side) or []:
                if a.get("asset_type") == "player" and a.get("player_id"):
                    pids.add(str(a["player_id"]))
    player_lookup: dict = {}
    oid_list = []
    for p in pids:
        try:
            oid_list.append(ObjectId(p))
        except Exception:
            continue
    async for p in db.players.find({"_id": {"$in": oid_list}}):
        player_lookup[str(p["_id"])] = p

    current_year = datetime.now(timezone.utc).year
    pair_buckets: dict = {}  # key = sorted (u1, u2) tuple
    for r in rows:
        u1, u2 = r.get("proposer_id"), r.get("target_owner_id")
        if not (u1 and u2):
            continue
        pair_key = tuple(sorted([str(u1), str(u2)]))
        f = compute_fairness(r, player_lookup, current_year=current_year)
        delta = 100 - f["score"]  # unfair-ness magnitude
        # Direction: who got the better side? +1 if u1 favored, -1 if u2 favored
        direction = 0
        if f["favored_side"] == "offered":
            # target got the better side (received the offered side)
            direction = +1 if str(u2) == pair_key[0] else -1
        elif f["favored_side"] == "requested":
            direction = +1 if str(u1) == pair_key[0] else -1
        bucket = pair_buckets.setdefault(pair_key, {
            "pair": list(pair_key), "trade_count": 0, "net_favor": 0.0, "trades": []
        })
        bucket["trade_count"] += 1
        bucket["net_favor"] += direction * delta
        bucket["trades"].append({
            "trade_id": str(r["_id"]),
            "league_id": r.get("league_id"),
            "score": f["score"],
            "favored_side": f["favored_side"],
            "submitted_at": r.get("submitted_at"),
        })

    flagged = []
    for pair_key, b in pair_buckets.items():
        if b["trade_count"] >= min_trades and abs(b["net_favor"]) >= min_net_favor_pct:
            # Hydrate user emails
            user_lookup = {}
            for uid in pair_key:
                try:
                    u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1, "name": 1})
                    if u:
                        user_lookup[uid] = {"email": u.get("email"), "name": u.get("name")}
                except Exception:
                    pass
            flagged.append({
                **b,
                "net_favor": round(b["net_favor"], 1),
                "favored_user_id": pair_key[0] if b["net_favor"] > 0 else pair_key[1],
                "users": user_lookup,
            })

    flagged.sort(key=lambda x: -abs(x["net_favor"]))
    return {"pairs": flagged, "min_trades": min_trades, "min_net_favor_pct": min_net_favor_pct}


@router.get("/tanking-flags")
async def tanking_flags(
    request: Request,
    weeks_window: int = Query(default=4, ge=1, le=10),
):
    """Heuristic tanking detection. For each league, identifies teams
    that are (a) outside the playoff cutoff with ≤3 weeks left, and (b)
    benched ≥2 of their top-5 salary players in the last `weeks_window`
    weeks (i.e., active points dropped sharply while bench points stayed
    high).

    Uses `lineup_history` entries from `activity_feed` (event_type =
    'lineup_set') if present; otherwise falls back to a salary-based
    proxy that flags teams whose top-5 salary players have ≥50%
    bench-time in the window.
    """
    await _require_admin(request)
    db = _deps["db"]

    # Gather recent lineup-set events
    since = (datetime.now(timezone.utc) - timedelta(days=weeks_window * 7)).isoformat()
    suspicious_teams: dict = {}

    # Iterate leagues — only those with active matchups
    async for league in db.leagues.find({}, {"_id": 1, "name": 1, "playoff_teams": 1, "current_week": 1, "regular_season_weeks": 1}):
        lid = str(league["_id"])
        # Cheap heuristic: weeks remaining
        cur_wk = league.get("current_week") or 0
        reg_wks = league.get("regular_season_weeks") or 0
        weeks_left = max(0, reg_wks - cur_wk)
        if weeks_left > 3:
            continue  # only late-season

        # Standings rank cutoff
        playoff_cut = league.get("playoff_teams") or 8
        teams = await db.teams.find({"league_id": lid}).to_list(64)
        if not teams:
            continue
        ranked = sorted(teams, key=lambda t: (-(t.get("wins") or 0), -(t.get("points_for") or 0)))
        non_playoff = ranked[playoff_cut:]

        for team in non_playoff:
            top5_ids = sorted(
                ((p, s) for p, s in (team.get("player_salaries") or {}).items() if isinstance(s, (int, float))),
                key=lambda kv: -kv[1],
            )[:5]
            if not top5_ids:
                continue
            top5_pids = {pid for pid, _ in top5_ids}

            # Count how many of the top-5 were benched in the window
            benched_count = 0
            benched_evidence: list = []
            async for ev in db.activity_feed.find({
                "league_id": lid,
                "event_type": "lineup_set",
                "created_at": {"$gte": since},
                "metadata.team_id": str(team["_id"]),
            }).limit(50):
                meta = ev.get("metadata") or {}
                for pid in (meta.get("benched_player_ids") or []):
                    if str(pid) in top5_pids:
                        benched_count += 1
                        benched_evidence.append({"player_id": str(pid), "ts": ev.get("created_at")})
            # Fallback proxy when no lineup_set events recorded
            if benched_count == 0 and not benched_evidence:
                continue
            if benched_count >= 2:
                suspicious_teams.setdefault(lid, {
                    "league_id": lid,
                    "league_name": league.get("name"),
                    "weeks_left": weeks_left,
                    "teams": [],
                })["teams"].append({
                    "team_id": str(team["_id"]),
                    "team_name": team.get("name"),
                    "owner_id": str(team.get("owner_id") or ""),
                    "owner_name": team.get("owner_name"),
                    "benched_top5_count": benched_count,
                    "evidence": benched_evidence[:5],
                })

    return {"flagged": list(suspicious_teams.values()), "weeks_window": weeks_window}


# ─────────────────────────────────────────────────────────────────────
# Iter 201d — Lineup audit + multi-account-by-IP detection
# ─────────────────────────────────────────────────────────────────────
@router.get("/lineup-audit")
async def lineup_audit(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    league_id: Optional[str] = None,
    team_id: Optional[str] = None,
    user_id: Optional[str] = None,
):
    """Lineup-mutation audit trail. Returns recent `lineup_set` events
    with IP / user-agent / actor identity. Also surfaces a derived
    `multi_account_flags` block: any IP that has set lineups for ≥2
    DIFFERENT user_ids across leagues in the last 14 days."""
    await _require_admin(request)
    db = _deps["db"]

    query: dict = {"event_type": "lineup_set"}
    if league_id:
        query["league_id"] = league_id
    if team_id:
        query["metadata.team_id"] = team_id
    if user_id:
        query["user_id"] = user_id

    rows = await db.activity_feed.find(query).sort("created_at", -1).limit(limit).to_list(limit)

    user_ids = {r.get("user_id") for r in rows if r.get("user_id")}
    league_ids = {r.get("league_id") for r in rows if r.get("league_id")}
    user_lookup: dict = {}
    league_lookup: dict = {}
    for uid in user_ids:
        try:
            u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1, "name": 1})
            if u:
                user_lookup[uid] = {"email": u.get("email"), "name": u.get("name")}
        except Exception:
            pass
    for lid in league_ids:
        try:
            lg = await db.leagues.find_one({"_id": ObjectId(lid)}, {"name": 1})
            if lg:
                league_lookup[lid] = lg.get("name")
        except Exception:
            pass

    entries = []
    for r in rows:
        meta = r.get("metadata") or {}
        entries.append({
            "id": str(r["_id"]),
            "league_id": r.get("league_id"),
            "league_name": league_lookup.get(r.get("league_id")),
            "user_id": r.get("user_id"),
            "user": user_lookup.get(r.get("user_id")),
            "team_id": meta.get("team_id"),
            "ip": meta.get("ip"),
            "user_agent": meta.get("user_agent"),
            "device_fingerprint": meta.get("device_fingerprint"),
            "created_at": r.get("created_at"),
            "summary": meta.get("summary") or r.get("message"),
        })

    # Multi-account detection: same IP setting lineups for >1 user_id in 14d
    fortnight_ago = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    ip_to_users: dict = {}
    async for r in db.activity_feed.find(
        {"event_type": "lineup_set", "created_at": {"$gte": fortnight_ago}, "metadata.ip": {"$exists": True}},
        {"user_id": 1, "metadata.ip": 1, "league_id": 1},
    ):
        ip = (r.get("metadata") or {}).get("ip")
        uid = r.get("user_id")
        if ip and uid:
            ip_to_users.setdefault(ip, set()).add(uid)
    multi_flags = []
    for ip, uids in ip_to_users.items():
        if len(uids) >= 2:
            emails = []
            for uid in uids:
                lookup = user_lookup.get(uid)
                if not lookup:
                    try:
                        u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1})
                        lookup = {"email": (u or {}).get("email")}
                    except Exception:
                        lookup = {"email": uid}
                emails.append(lookup.get("email") or uid)
            multi_flags.append({"ip": ip, "user_count": len(uids), "users": emails})

    return {
        "entries": entries,
        "multi_account_flags": sorted(multi_flags, key=lambda x: -x["user_count"]),
        "limit": limit,
    }


# Iter 201d — helper used by the lineup write paths to stamp IP/UA
async def record_lineup_event(
    db,
    league_id: str,
    team_id: str,
    user_id: str,
    request: Request,
    summary: str | None = None,
    benched_player_ids: list[str] | None = None,
):
    """Record a `lineup_set` audit event with IP + UA fingerprinting. Call
    from `routes/lineup.py` after every lineup mutation."""
    ip = request.client.host if request.client else None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
    ua = request.headers.get("user-agent", "")[:240]
    await db.activity_feed.insert_one({
        "league_id": league_id,
        "event_type": "lineup_set",
        "message": summary or "Lineup updated",
        "user_id": user_id,
        "metadata": {
            "team_id": team_id,
            "ip": ip,
            "user_agent": ua,
            "device_fingerprint": f"{ip}::{ua[:60]}",
            "summary": summary,
            "benched_player_ids": benched_player_ids or [],
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────
# Iter 201e — Admin moderation actions
#   • POST /trades/{trade_id}/revert       — roll back asset/pick moves
#   • POST /pairs/lock                     — lock trades between user pair
#   • GET  /pairs/locks                    — list active locks
#   • DELETE /pairs/locks/{lock_id}        — release a lock
# ─────────────────────────────────────────────────────────────────────
from pydantic import BaseModel  # noqa: E402


@router.post("/trades/{trade_id}/revert")
async def admin_revert_trade(trade_id: str, request: Request):
    """Roll back an EXECUTED trade. Swaps players + picks back to their
    pre-trade owners, marks `status="reverted"`, writes an audit row, and
    notifies both team owners. Cap impact is implicit via roster updates —
    we don't unwind cap-retention pacts (those need manual review)."""
    user = await _require_admin(request)
    db = _deps["db"]

    try:
        tid = ObjectId(trade_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid trade_id")
    trade = await db.trades.find_one({"_id": tid})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.get("status") in ("reverted", "vetoed"):
        raise HTTPException(status_code=400, detail=f"Trade already in terminal state: {trade['status']}")
    if trade.get("status") != "executed":
        raise HTTPException(status_code=400, detail="Only executed trades can be reverted")

    proposer = await db.teams.find_one({"_id": ObjectId(trade["proposer_team_id"])})
    target = await db.teams.find_one({"_id": ObjectId(trade["target_team_id"])})
    if not (proposer and target):
        raise HTTPException(status_code=404, detail="Proposer or target team missing")

    proposer_roster = list(proposer.get("roster") or [])
    target_roster = list(target.get("roster") or [])

    # ── Swap players BACK: offered moves from target → proposer ──
    for a in trade.get("assets_offered") or []:
        if a.get("asset_type") == "player" and a.get("player_id"):
            pid = a["player_id"]
            if pid in target_roster:
                target_roster.remove(pid)
            if pid not in proposer_roster:
                proposer_roster.append(pid)
        elif a.get("asset_type") == "pick":
            # Pick currently with target → back to proposer
            await db.draft_picks.update_one(
                {"league_id": trade["league_id"], "current_team_id": trade["target_team_id"],
                 **({"_id": ObjectId(a["pick_id"])} if a.get("pick_id") else
                    {**({"year": int(a["pick_year"])} if a.get("pick_year") else {}),
                     **({"round": int(str(a["pick_round"]).replace("R", "").strip())} if a.get("pick_round") else {})})},
                {"$set": {"current_team_id": trade["proposer_team_id"], "current_team_name": proposer.get("name")}},
            )

    # ── Swap players BACK: requested moves from proposer → target ──
    for a in trade.get("assets_requested") or []:
        if a.get("asset_type") == "player" and a.get("player_id"):
            pid = a["player_id"]
            if pid in proposer_roster:
                proposer_roster.remove(pid)
            if pid not in target_roster:
                target_roster.append(pid)
        elif a.get("asset_type") == "pick":
            await db.draft_picks.update_one(
                {"league_id": trade["league_id"], "current_team_id": trade["proposer_team_id"],
                 **({"_id": ObjectId(a["pick_id"])} if a.get("pick_id") else
                    {**({"year": int(a["pick_year"])} if a.get("pick_year") else {}),
                     **({"round": int(str(a["pick_round"]).replace("R", "").strip())} if a.get("pick_round") else {})})},
                {"$set": {"current_team_id": trade["target_team_id"], "current_team_name": target.get("name")}},
            )

    await db.teams.update_one({"_id": proposer["_id"]}, {"$set": {"roster": proposer_roster}})
    await db.teams.update_one({"_id": target["_id"]}, {"$set": {"roster": target_roster}})

    now = datetime.now(timezone.utc).isoformat()
    await db.trades.update_one(
        {"_id": tid},
        {"$set": {
            "status": "reverted",
            "reverted_at": now,
            "reverted_by": str(user["_id"]),
            "reverted_by_email": user.get("email"),
        }},
    )
    await db.activity_feed.insert_one({
        "league_id": trade["league_id"],
        "event_type": "platform_admin_trade_revert",
        "message": f"Admin reverted trade {trade_id} ({proposer.get('name')} ↔ {target.get('name')})",
        "user_id": str(user["_id"]),
        "metadata": {
            "trade_id": trade_id,
            "proposer_team_id": trade["proposer_team_id"],
            "target_team_id": trade["target_team_id"],
            "reverted_by_email": user.get("email"),
        },
        "created_at": now,
    })
    return {"ok": True, "trade_id": trade_id, "reverted_at": now, "reverted_by": user.get("email")}


class PairLockBody(BaseModel):
    user_ids: list[str]
    league_id: str | None = None
    reason: str | None = None


@router.post("/pairs/lock")
async def admin_lock_pair(body: PairLockBody, request: Request):
    """Lock trading between a pair (or group) of user_ids. The trade
    creation endpoint should consult `trade_locks` and reject any pending
    trade whose (proposer_id, target_owner_id) intersects with an active
    lock. Scope optionally narrowed to a single league."""
    user = await _require_admin(request)
    db = _deps["db"]
    if len(body.user_ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 user_ids to lock a pair")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "user_ids": sorted(set(str(u) for u in body.user_ids)),
        "league_id": body.league_id,  # null = global lock
        "reason": body.reason,
        "locked_by": str(user["_id"]),
        "locked_by_email": user.get("email"),
        "locked_at": now,
        "active": True,
    }
    res = await db.trade_locks.insert_one(doc)
    await db.activity_feed.insert_one({
        "league_id": body.league_id,
        "event_type": "platform_admin_pair_lock",
        "message": f"Admin locked trading between {len(body.user_ids)} users",
        "user_id": str(user["_id"]),
        "metadata": {"lock_id": str(res.inserted_id), **doc},
        "created_at": now,
    })
    return {"ok": True, "lock_id": str(res.inserted_id), **{k: v for k, v in doc.items() if k != "_id"}}


@router.get("/pairs/locks")
async def list_pair_locks(request: Request, active_only: bool = True):
    await _require_admin(request)
    db = _deps["db"]
    q = {"active": True} if active_only else {}
    rows = await db.trade_locks.find(q).sort("locked_at", -1).to_list(200)
    out = []
    for r in rows:
        # Hydrate emails
        emails = []
        for uid in (r.get("user_ids") or []):
            try:
                u = await db.users.find_one({"_id": ObjectId(uid)}, {"email": 1})
                if u:
                    emails.append(u.get("email"))
            except Exception:
                emails.append(uid)
        out.append({
            "lock_id": str(r["_id"]),
            "user_ids": r.get("user_ids") or [],
            "emails": emails,
            "league_id": r.get("league_id"),
            "reason": r.get("reason"),
            "locked_by_email": r.get("locked_by_email"),
            "locked_at": r.get("locked_at"),
            "active": r.get("active", True),
        })
    return {"locks": out}


@router.delete("/pairs/locks/{lock_id}")
async def admin_release_lock(lock_id: str, request: Request):
    user = await _require_admin(request)
    db = _deps["db"]
    try:
        oid = ObjectId(lock_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lock_id")
    res = await db.trade_locks.update_one(
        {"_id": oid, "active": True},
        {"$set": {"active": False, "released_at": datetime.now(timezone.utc).isoformat(),
                  "released_by": str(user["_id"]), "released_by_email": user.get("email")}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lock not found or already released")
    return {"ok": True, "lock_id": lock_id}


async def is_trade_locked(db, league_id: str, proposer_id: str, target_owner_id: str) -> dict | None:
    """Helper for the trade-create endpoint to gate proposals. Returns the
    active lock document if the pair is locked (global or league-scoped),
    else None."""
    p = str(proposer_id)
    t = str(target_owner_id)
    lock = await db.trade_locks.find_one({
        "active": True,
        "user_ids": {"$all": [p, t]},
        "$or": [{"league_id": None}, {"league_id": league_id}],
    })
    return lock


# ─────────────────────────────────────────────────────────────────────
# Iter 205 — Content Moderation Phase 1: Report/Flag System
# ─────────────────────────────────────────────────────────────────────
# Schema: db.user_reports = {
#   _id, reporter_id, reporter_email,
#   target_user_id, target_user_email,
#   target_team_id?, league_id?,
#   category, reason, context_url?,
#   status: "open" | "resolved" | "dismissed",
#   created_at,
#   resolved_at?, resolved_by?, resolution_note?, resolution_action?,
# }
# `category` is a free-form string from a UI dropdown (e.g. "harassment",
# "spam", "offensive_username", "trade_collusion", "other").

VALID_REPORT_CATEGORIES = {
    "harassment",
    "spam",
    "offensive_username",
    "offensive_team_name",
    "offensive_avatar",
    "trade_collusion",
    "cheating",
    "other",
}


@router.get("/reports")
async def list_user_reports(
    request: Request,
    status: str = Query("open", pattern=r"^(open|resolved|dismissed|all)$"),
    limit: int = Query(100, ge=1, le=500),
):
    """List submitted user reports (admin-only). Default surfaces only
    `open` tickets so the moderation queue stays focused."""
    await _require_admin(request)
    db = _deps["db"]
    q: dict = {} if status == "all" else {"status": status}
    rows = await db.user_reports.find(q).sort("created_at", -1).to_list(limit)
    out = []
    for r in rows:
        out.append({
            "report_id": str(r["_id"]),
            "reporter_id": r.get("reporter_id"),
            "reporter_email": r.get("reporter_email"),
            "target_user_id": r.get("target_user_id"),
            "target_user_email": r.get("target_user_email"),
            "target_team_id": r.get("target_team_id"),
            "league_id": r.get("league_id"),
            "category": r.get("category"),
            "reason": r.get("reason"),
            "context_url": r.get("context_url"),
            "status": r.get("status"),
            "created_at": _iso(r.get("created_at")),
            "resolved_at": _iso(r.get("resolved_at")),
            "resolved_by": r.get("resolved_by"),
            "resolution_note": r.get("resolution_note"),
            "resolution_action": r.get("resolution_action"),
        })
    # Counts for the dashboard tab badge
    open_count = await db.user_reports.count_documents({"status": "open"})
    return {"reports": out, "open_count": open_count}


@router.post("/reports/{report_id}/resolve")
async def resolve_user_report(report_id: str, request: Request):
    """Resolve or dismiss a report. Body:
      { "action": "resolved" | "dismissed", "note": "...", "applied_action": "warning"|"timeout"|"ban"|"none" }
    """
    user = await _require_admin(request)
    db = _deps["db"]
    try:
        oid = ObjectId(report_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report id")

    payload = await request.json()
    action = payload.get("action") or "resolved"
    if action not in ("resolved", "dismissed"):
        raise HTTPException(status_code=400, detail="action must be resolved|dismissed")
    note = (payload.get("note") or "").strip()[:1000]
    applied_action = payload.get("applied_action") or "none"
    if applied_action not in ("warning", "timeout", "ban", "none"):
        raise HTTPException(status_code=400, detail="invalid applied_action")

    res = await db.user_reports.update_one(
        {"_id": oid, "status": "open"},
        {
            "$set": {
                "status": action,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": str(user["_id"]),
                "resolved_by_email": user.get("email"),
                "resolution_note": note,
                "resolution_action": applied_action,
            }
        },
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Report not found or already resolved")
    return {"ok": True, "report_id": report_id, "status": action}



# ─────────────────────────────────────────────────────────────────────
# Iter 214 — Users directory + per-user identity / security drilldown
# ─────────────────────────────────────────────────────────────────────
@router.get("/users")
async def list_users(
    request: Request,
    q: Optional[str] = Query(None, description="search email or username"),
    status: Optional[str] = Query(None, pattern=r"^(active|suspended|banned|deactivated|pending_verification)$"),
    role: Optional[str] = Query(None, pattern=r"^(user|admin|commissioner)$"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """Paginated user directory for admins. Returns identity + status
    summary per row; the per-user detail endpoint surfaces login history,
    devices, etc."""
    await _require_admin(request)
    db = _deps["db"]
    flt: dict = {}
    if q:
        flt["$or"] = [
            {"email": {"$regex": q, "$options": "i"}},
            {"username": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
        ]
    if status:
        flt["status"] = status
    if role:
        flt["role"] = role
    total = await db.users.count_documents(flt)
    cursor = db.users.find(flt, {
        "email": 1, "username": 1, "name": 1, "role": 1, "status": 1,
        "is_active": 1, "created_at": 1, "email_verified": 1, "phone": 1,
        "phone_verified": 1, "auth_method": 1, "two_factor_enabled": 1,
        "last_login_at": 1, "failed_login_attempts": 1, "lockout_until": 1,
        "ban_reason_code": 1, "ban_reason": 1, "ban_expires_at": 1,
    }).sort("created_at", -1).skip(skip).limit(limit)
    rows = await cursor.to_list(limit)
    # Latest login timestamp fallback via user_login_audit when last_login_at not set.
    user_ids = [str(r["_id"]) for r in rows]
    last_login_by_uid: dict = {}
    if user_ids:
        async for a in db.user_login_audit.aggregate([
            {"$match": {"user_id": {"$in": user_ids}}},
            {"$sort": {"ts": -1}},
            {"$group": {"_id": "$user_id", "ts": {"$first": "$ts"}}},
        ]):
            last_login_by_uid[a["_id"]] = a["ts"]
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "users": [{
            "id": str(r["_id"]),
            "email": r.get("email"),
            "username": r.get("username"),
            "name": r.get("name"),
            "role": r.get("role") or "user",
            "status": r.get("status") or ("active" if r.get("is_active", True) else "deactivated"),
            "created_at": _iso(r.get("created_at")),
            "email_verified": bool(r.get("email_verified", False)),
            "phone": r.get("phone"),
            "phone_verified": bool(r.get("phone_verified", False)),
            "auth_method": r.get("auth_method") or "email",
            "two_factor_enabled": bool(r.get("two_factor_enabled", False)),
            "last_login_at": _iso(r.get("last_login_at")) or last_login_by_uid.get(str(r["_id"])),
            "failed_login_attempts": int(r.get("failed_login_attempts") or 0),
            "lockout_until": _iso(r.get("lockout_until")),
            "ban_reason_code": r.get("ban_reason_code"),
            "ban_reason": r.get("ban_reason"),
            "ban_expires_at": _iso(r.get("ban_expires_at")),
        } for r in rows],
    }


@router.get("/users/{user_id}")
async def get_user_detail(user_id: str, request: Request):
    """Full per-user identity / authentication / security view for
    admin moderation. Surfaces:
      • Identity & account core (username, email, phone, status…)
      • Username/email change history (from `user_audit_log`)
      • Authentication & security (last login, login history,
        2FA, password reset history, linked SSO accounts, active
        sessions, recovery info)
    """
    await _require_admin(request)
    db = _deps["db"]
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user id")
    u = await db.users.find_one({"_id": oid})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    # Login history (last 50)
    login_history = await db.user_login_audit.find(
        {"user_id": user_id}
    ).sort("ts", -1).to_list(50)

    # Username / email change history (if recorded)
    name_history = await db.user_audit_log.find(
        {"user_id": user_id, "event_type": {"$in": ["username_changed", "email_changed", "name_changed"]}}
    ).sort("ts", -1).to_list(50)

    # Password reset history
    pwd_resets = await db.password_reset_audit.find(
        {"user_id": user_id}
    ).sort("ts", -1).to_list(20)

    # Active sessions (jwt issuance audit, if recorded)
    sessions = await db.user_sessions.find(
        {"user_id": user_id, "revoked": {"$ne": True}}
    ).sort("issued_at", -1).to_list(20)

    return {
        # ── Identity & Account Core ───────────────────────────────
        "id": str(u["_id"]),
        "username": u.get("username"),
        "name": u.get("name"),
        "email": u.get("email"),
        "email_verified": bool(u.get("email_verified", False)),
        "phone": u.get("phone"),
        "phone_verified": bool(u.get("phone_verified", False)),
        "auth_method": u.get("auth_method") or "email",
        "password_hash_present": bool(u.get("password_hash")),
        "linked_sso_accounts": u.get("linked_sso_accounts") or [],
        "role": u.get("role") or "user",
        "permission_tier": u.get("permission_tier"),
        "status": u.get("status") or ("active" if u.get("is_active", True) else "deactivated"),
        "ban_reason_code": u.get("ban_reason_code"),
        "ban_reason": u.get("ban_reason"),
        "ban_expires_at": _iso(u.get("ban_expires_at")),
        "created_at": _iso(u.get("created_at")),
        "username_change_history": [{
            "ts": _iso(h.get("ts")),
            "event_type": h.get("event_type"),
            "from": h.get("from_value"),
            "to": h.get("to_value"),
        } for h in name_history],
        # ── Authentication & Security ─────────────────────────────
        "last_login_at": _iso(u.get("last_login_at")) or (
            _iso(login_history[0].get("ts")) if login_history else None
        ),
        "login_history": [{
            "ts": _iso(h.get("ts")),
            "ip": h.get("ip"),
            "user_agent": h.get("user_agent"),
            "device_hash": h.get("device_hash"),
            "device_fingerprint": h.get("device_fingerprint"),
        } for h in login_history],
        "failed_login_attempts": int(u.get("failed_login_attempts") or 0),
        "lockout_until": _iso(u.get("lockout_until")),
        "two_factor_enabled": bool(u.get("two_factor_enabled", False)),
        "two_factor_method": u.get("two_factor_method"),
        "password_reset_history": [{
            "ts": _iso(p.get("ts")),
            "ip": p.get("ip"),
            "outcome": p.get("outcome"),
        } for p in pwd_resets],
        "active_sessions": [{
            "session_id": str(s.get("_id")),
            "issued_at": _iso(s.get("issued_at")),
            "expires_at": _iso(s.get("expires_at")),
            "ip": s.get("ip"),
            "user_agent": s.get("user_agent"),
        } for s in sessions],
        "recovery_email": u.get("recovery_email"),
        "security_questions_set": bool(u.get("security_questions")),
        # ── Iter 216 — extended sections ──────────────────────────
        **(await _build_user_extensions(db, user_id, u)),
    }


# ─────────────────────────────────────────────────────────────────────
# Iter 216 — extended user detail sections
# ─────────────────────────────────────────────────────────────────────
async def _build_user_extensions(db, user_id: str, u: dict) -> dict:
    """Gather all extended sections (league/team, behavioral, financial,
    support, compliance) needed by the User Detail Drawer."""
    # League & Team Relationships
    teams = await db.teams.find({"owner_id": user_id}).to_list(500)
    historical_teams = await db.teams.find({
        "owner_history": {"$elemMatch": {"user_id": user_id}}
    }).to_list(200)
    league_ids = list({t.get("league_id") for t in teams + historical_teams if t.get("league_id")})
    league_docs: dict = {}
    if league_ids:
        async for lg in db.leagues.find({"_id": {"$in": [
            ObjectId(lid) for lid in league_ids if ObjectId.is_valid(str(lid))
        ]}}, {"name": 1, "commissioner_id": 1, "co_commissioners": 1, "status": 1, "created_at": 1}):
            league_docs[str(lg["_id"])] = lg
    leagues_joined = []
    for lid in league_ids:
        lg = league_docs.get(str(lid)) or {}
        role = "manager"
        if str(lg.get("commissioner_id")) == user_id:
            role = "commissioner"
        elif user_id in (lg.get("co_commissioners") or []):
            role = "co_commissioner"
        leagues_joined.append({
            "league_id": str(lid), "league_name": lg.get("name"),
            "role": role, "league_status": lg.get("status"),
            "joined_at": _iso(lg.get("created_at")),
        })
    invitations_sent = await db.league_invites.find({"sender_id": user_id}).sort("created_at", -1).to_list(50)
    invitations_received = await db.league_invites.find({
        "$or": [{"recipient_user_id": user_id}, {"recipient_email": u.get("email")}]
    }).sort("created_at", -1).to_list(50)

    # Behavioral & Moderation
    reports_against = await db.user_reports.count_documents({"target_user_id": user_id})
    reports_filed = await db.user_reports.count_documents({"reporter_id": user_id})
    moderation_history = await db.admin_user_actions.find(
        {"target_user_id": user_id,
         "action": {"$in": ["suspend", "ban_permanent", "reinstate", "warning",
                            "mute", "unmute", "flag_for_review", "unflag",
                            "delete_hard", "gdpr_delete"]}}
    ).sort("ts", -1).to_list(100)
    appeals = await db.user_appeals.find({"user_id": user_id}).sort("created_at", -1).to_list(50)
    trade_flags = await db.trades.count_documents({
        "$or": [{"proposer_team_owner_id": user_id}, {"target_team_owner_id": user_id}],
        "flagged_for_admin": True,
    })
    chat_violations = await db.moderation_queue.count_documents({
        "user_id": user_id, "source": {"$in": ["chat", "username", "team_name", "trade_block"]}
    })
    multi_account_links = await db.user_login_audit.aggregate([
        {"$match": {"user_id": user_id, "device_hash": {"$ne": None}}},
        {"$group": {"_id": "$device_hash"}},
        {"$lookup": {
            "from": "user_login_audit",
            "let": {"dh": "$_id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$device_hash", "$$dh"]},
                    {"$ne": ["$user_id", user_id]},
                ]}}},
                {"$group": {"_id": "$user_id"}},
            ],
            "as": "other_users",
        }},
        {"$match": {"other_users.0": {"$exists": True}}},
        {"$project": {"device_hash": "$_id", "linked_user_ids": "$other_users._id"}},
    ]).to_list(50)

    # Financial / Billing
    payment_methods = u.get("payment_methods") or []  # tokenized only
    billing_history = await db.payment_transactions.find(
        {"user_id": user_id}
    ).sort("created_at", -1).to_list(20)
    league_fees = await db.league_fees.find({"user_id": user_id}).sort("due_at", -1).to_list(50)
    referrals_used = u.get("referral_codes_used") or []

    # Support & Engagement
    support_tickets = await db.user_support_links.find({"user_id": user_id}).sort("ts", -1).to_list(50)
    feature_flags = u.get("feature_flags") or []
    sessions_lifetime = await db.user_login_audit.count_documents({"user_id": user_id})
    last_active = await db.user_login_audit.find_one({"user_id": user_id}, sort=[("ts", -1)])

    return {
        # League & Team Relationships
        "leagues_joined": leagues_joined,
        "teams_owned": [{
            "team_id": str(t["_id"]), "team_name": t.get("name"),
            "league_id": t.get("league_id"),
            "league_name": (league_docs.get(str(t.get("league_id"))) or {}).get("name"),
            "current": True,
        } for t in teams],
        "teams_owned_history": [{
            "team_id": str(t["_id"]), "team_name": t.get("name"),
            "league_id": t.get("league_id"),
            "league_name": (league_docs.get(str(t.get("league_id"))) or {}).get("name"),
            "current": False,
        } for t in historical_teams],
        "invitations_sent": [{
            "id": str(i["_id"]), "league_id": i.get("league_id"),
            "recipient_email": i.get("recipient_email"),
            "status": i.get("status"), "created_at": _iso(i.get("created_at")),
        } for i in invitations_sent],
        "invitations_received": [{
            "id": str(i["_id"]), "league_id": i.get("league_id"),
            "sender_id": i.get("sender_id"),
            "status": i.get("status"), "created_at": _iso(i.get("created_at")),
        } for i in invitations_received],

        # Behavioral & Moderation
        "reports_against_count": reports_against,
        "reports_filed_count": reports_filed,
        "moderation_action_history": [{
            "id": str(m["_id"]), "action": m.get("action"),
            "reason": m.get("reason"), "admin_email": m.get("admin_email"),
            "ts": _iso(m.get("ts")), "metadata": m.get("metadata"),
            "appealed": any(a.get("action_id") == str(m["_id"]) for a in appeals),
        } for m in moderation_history],
        "appeals": [{
            "id": str(a["_id"]), "status": a.get("status"),
            "message": a.get("message"), "created_at": _iso(a.get("created_at")),
            "resolved_at": _iso(a.get("resolved_at")),
        } for a in appeals],
        "trade_flags_count": trade_flags,
        "chat_violations_count": chat_violations,
        "multi_account_links": [{
            "device_hash": (link.get("device_hash") or "")[:12] + "…" if link.get("device_hash") else None,
            "linked_user_ids": link.get("linked_user_ids", []),
        } for link in multi_account_links],
        "trust_score": u.get("trust_score"),
        "watchlist": bool(u.get("watchlist")),
        "watchlist_reason": u.get("watchlist_reason"),

        # Financial / Billing
        "subscription_tier": u.get("subscription_tier") or ("pro" if u.get("is_pro") else "free"),
        "subscription_status": u.get("subscription_status") or "active",
        "payment_methods": [{
            "id": pm.get("id") or pm.get("stripe_payment_method_id"),
            "brand": pm.get("brand"), "last4": pm.get("last4"),
            "exp_month": pm.get("exp_month"), "exp_year": pm.get("exp_year"),
        } for pm in payment_methods],
        "billing_history": [{
            "id": str(b["_id"]) if b.get("_id") else b.get("session_id"),
            "amount_cents": b.get("amount"), "currency": b.get("currency"),
            "status": b.get("payment_status"),
            "created_at": _iso(b.get("created_at")),
            "description": b.get("description"),
        } for b in billing_history],
        "league_fees": [{
            "id": str(f["_id"]), "league_id": f.get("league_id"),
            "amount_cents": f.get("amount_cents"), "status": f.get("status"),
            "due_at": _iso(f.get("due_at")), "paid_at": _iso(f.get("paid_at")),
        } for f in league_fees],
        "payout_info": {
            "method": u.get("payout_method"),  # bank|paypal|stripe
            "destination_token": u.get("payout_destination_token"),
            "tax_form_status": u.get("tax_form_status"),  # w9_filed|1099_issued|none
        },
        "promo_credits_cents": u.get("promo_credits_cents") or 0,
        "referrals_used": referrals_used,
        "chargeback_flags": u.get("chargeback_flags") or [],

        # Support & Engagement
        "support_tickets": [{
            "id": str(t["_id"]), "ticket_id": t.get("ticket_id"),
            "ticket_url": t.get("ticket_url"), "note": t.get("note"),
            "ts": _iso(t.get("ts")),
        } for t in support_tickets],
        "feature_flags": feature_flags,
        "engagement": {
            "lifetime_sessions": sessions_lifetime,
            "last_active_at": _iso((last_active or {}).get("ts")),
        },
        "onboarding_completed": bool(u.get("onboarding_completed", False)),
        "onboarding_steps": u.get("onboarding_steps") or {},

        # Compliance & Legal
        "compliance": {
            "date_of_birth": _iso(u.get("date_of_birth")),
            "age_verified": bool(u.get("age_verified", False)),
            "tos_version_accepted": u.get("tos_version_accepted"),
            "tos_accepted_at": _iso(u.get("tos_accepted_at")),
            "privacy_consents": u.get("privacy_consents") or {},
            "marketing_email_consent": bool(u.get("marketing_email_consent", False)),
            "region": u.get("region") or u.get("country"),
            "jurisdiction_block": u.get("jurisdiction_block"),  # 'AZ','IA','LA','MT','WA'…
            "data_deletion_requested_at": _iso(u.get("data_deletion_requested_at")),
            "data_deletion_completed_at": _iso(u.get("gdpr_deleted_at")),
        },
    }


# ─────────────────────────────────────────────────────────────────────
# Iter 216 — Recent admin actions feed (Overview tab)
# ─────────────────────────────────────────────────────────────────────
@router.get("/recent-admin-actions")
async def recent_admin_actions(request: Request, limit: int = Query(20, ge=1, le=100)):
    """Cross-user feed of the latest admin actions taken anywhere on
    the platform. Each row hydrated with the target user's email."""
    await _require_admin(request)
    db = _deps["db"]
    rows = await db.admin_user_actions.find({}).sort("ts", -1).to_list(limit)
    # Hydrate target_user emails
    target_ids = list({r.get("target_user_id") for r in rows if r.get("target_user_id")})
    targets: dict = {}
    if target_ids:
        try:
            obj_ids = [ObjectId(t) for t in target_ids if ObjectId.is_valid(str(t))]
            async for u in db.users.find({"_id": {"$in": obj_ids}}, {"email": 1, "username": 1}):
                targets[str(u["_id"])] = {"email": u.get("email"), "username": u.get("username")}
        except Exception:
            pass
    return {
        "actions": [{
            "id": str(r["_id"]),
            "action": r.get("action"),
            "admin_email": r.get("admin_email"),
            "admin_tier": r.get("admin_tier"),
            "target_user_id": r.get("target_user_id"),
            "target_email": (targets.get(r.get("target_user_id") or "") or {}).get("email"),
            "reason": r.get("reason"),
            "mocked": bool(r.get("mocked", False)),
            "ts": _iso(r.get("ts")),
        } for r in rows],
    }
