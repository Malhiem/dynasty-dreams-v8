// Iter 230m — "Security" tab inside the Platform Admin dashboard.
//
// Renders the repo-root /app/SECURITY.md file (fetched via
// GET /api/admin/platform/security-doc) inline as a read-only reference.
// Keeps the audit findings + auth conventions accessible from the same
// surface admins use every day, instead of buried in a git path.
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { ShieldCheck, FileText, ExternalLink, Loader2, Clock, Download, Hash, Copy } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

type DocResponse = {
  path: string;
  bytes: number;
  modified_at: string | null;
  content: string;
  last_export?: {
    sha256: string;
    bytes: number;
    generated_at: string;
    generated_by?: string | null;
    filename?: string | null;
  } | null;
};

// Minimal markdown-to-React renderer — handles headings, paragraphs,
// unordered lists, fenced code, inline code, tables, links, and the
// blockquote we use at the doc's intro. Intentionally tiny: this is
// one trusted doc, not user-generated content, so we skip xss-safe
// escaping concerns (the source is committed to the repo).
function renderMarkdown(md: string) {
  const lines = md.split("\n");
  const nodes: React.ReactNode[] = [];
  let i = 0;
  let key = 0;
  const nextKey = () => `md-${key++}`;

  const inline = (s: string): React.ReactNode => {
    // Code spans first so links inside them stay literal.
    const parts: React.ReactNode[] = [];
    let buf = "";
    let inCode = false;
    for (let j = 0; j < s.length; j++) {
      if (s[j] === "`") {
        if (inCode) {
          parts.push(
            <code key={nextKey()} className="rounded bg-secondary/60 px-1 py-0.5 text-[12px] text-cyan-300">
              {buf}
            </code>,
          );
          buf = "";
          inCode = false;
        } else {
          if (buf) parts.push(<span key={nextKey()}>{buf}</span>);
          buf = "";
          inCode = true;
        }
        continue;
      }
      buf += s[j];
    }
    if (buf) parts.push(<span key={nextKey()}>{buf}</span>);
    // Bold + links applied to the assembled non-code chunks only.
    return parts.map((p, idx) => {
      if (typeof p !== "string" && (p as any)?.type === "code") return p;
      const txt = typeof p === "string" ? p : ((p as any).props?.children ?? "");
      let nodes2: React.ReactNode[] = [txt];
      // Markdown links [label](url)
      nodes2 = nodes2.flatMap((n) => {
        if (typeof n !== "string") return n;
        const out: React.ReactNode[] = [];
        const re = /\[([^\]]+)\]\(([^)]+)\)/g;
        let last = 0;
        let m: RegExpExecArray | null;
        while ((m = re.exec(n)) !== null) {
          if (m.index > last) out.push(n.slice(last, m.index));
          out.push(
            <a key={nextKey()} href={m[2]} target="_blank" rel="noreferrer"
               className="text-cyan-400 hover:underline">{m[1]}</a>,
          );
          last = m.index + m[0].length;
        }
        if (last < n.length) out.push(n.slice(last));
        return out;
      });
      // Bold **x**
      nodes2 = nodes2.flatMap((n) => {
        if (typeof n !== "string") return n;
        const out: React.ReactNode[] = [];
        const re = /\*\*([^*]+)\*\*/g;
        let last = 0;
        let m: RegExpExecArray | null;
        while ((m = re.exec(n)) !== null) {
          if (m.index > last) out.push(n.slice(last, m.index));
          out.push(<strong key={nextKey()} className="text-foreground">{m[1]}</strong>);
          last = m.index + m[0].length;
        }
        if (last < n.length) out.push(n.slice(last));
        return out;
      });
      return <span key={`${idx}-${nextKey()}`}>{nodes2}</span>;
    });
  };

  while (i < lines.length) {
    const ln = lines[i];

    // Fenced code block ``` … ```
    if (ln.trim().startsWith("```")) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        buf.push(lines[i]);
        i++;
      }
      i++;
      nodes.push(
        <pre key={nextKey()} className="rounded-md bg-secondary/40 border border-border p-3 text-[11px] leading-relaxed overflow-x-auto text-cyan-100 my-3">
          <code>{buf.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    // Markdown table — rows starting with `|` and a separator row `|---`
    if (ln.trimStart().startsWith("|") && (lines[i + 1] || "").includes("---")) {
      const header = ln.split("|").slice(1, -1).map((c) => c.trim());
      i += 2; // skip separator
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trimStart().startsWith("|")) {
        rows.push(lines[i].split("|").slice(1, -1).map((c) => c.trim()));
        i++;
      }
      nodes.push(
        <div key={nextKey()} className="my-3 overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/40">
              <tr>{header.map((h, hi) => <th key={hi} className="text-left px-3 py-2 font-semibold text-foreground">{inline(h)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri} className="border-t border-border/60">
                  {r.map((c, ci) => <td key={ci} className="px-3 py-2 align-top text-muted-foreground">{inline(c)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    // Unordered list (* or -)
    if (/^\s*[*-]\s+/.test(ln)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[*-]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[*-]\s+/, ""));
        i++;
      }
      nodes.push(
        <ul key={nextKey()} className="list-disc pl-6 space-y-1 my-2 text-sm text-muted-foreground">
          {items.map((it, idx) => <li key={idx}>{inline(it)}</li>)}
        </ul>,
      );
      continue;
    }

    if (ln.startsWith("### ")) {
      nodes.push(<h3 key={nextKey()} className="text-base font-semibold mt-5 mb-2 text-foreground">{inline(ln.slice(4))}</h3>);
      i++; continue;
    }
    if (ln.startsWith("## ")) {
      nodes.push(<h2 key={nextKey()} className="text-lg font-bold mt-6 mb-2 text-foreground border-b border-border/60 pb-1">{inline(ln.slice(3))}</h2>);
      i++; continue;
    }
    if (ln.startsWith("# ")) {
      nodes.push(<h1 key={nextKey()} className="text-xl font-bold mt-2 mb-3 text-foreground">{inline(ln.slice(2))}</h1>);
      i++; continue;
    }
    if (ln.startsWith("> ")) {
      nodes.push(
        <blockquote key={nextKey()} className="border-l-2 border-cyan-400/60 bg-cyan-400/5 px-3 py-1.5 my-2 text-sm text-muted-foreground italic">
          {inline(ln.slice(2))}
        </blockquote>,
      );
      i++; continue;
    }
    if (ln.trim() === "---" || ln.trim() === "***") {
      nodes.push(<hr key={nextKey()} className="my-4 border-border/60" />);
      i++; continue;
    }
    if (ln.trim() === "") {
      i++; continue;
    }
    nodes.push(<p key={nextKey()} className="my-2 text-sm text-muted-foreground leading-relaxed">{inline(ln)}</p>);
    i++;
  }
  return nodes;
}

export default function SecurityDocPanel() {
  const [doc, setDoc] = useState<DocResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  // Iter 230o — Export PDF button state.
  const [exporting, setExporting] = useState(false);

  const handleExportPdf = async () => {
    setExporting(true);
    try {
      const res = await api.get("/admin/platform/security-export.pdf", {
        responseType: "blob",
      });
      // Iter 230p — capture the chain-of-custody hash from the response
      // header so we can display it immediately (no extra round-trip).
      const sha256 = res.headers["x-pdf-sha256"] || res.headers["X-PDF-SHA256"];
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, "");
      const fname = `dynasty-dreams-security-${stamp}.pdf`;
      a.download = fname;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      // Optimistically update the panel's last_export so the user sees
      // the new hash instantly without re-fetching the doc.
      if (sha256) {
        setDoc((cur) => cur && ({
          ...cur,
          last_export: {
            sha256: String(sha256),
            bytes: blob.size,
            generated_at: new Date().toISOString(),
            generated_by: null,
            filename: fname,
          },
        }));
      }
      toast.success("Security audit bundle downloaded", {
        description: sha256 ? `SHA-256: ${String(sha256).slice(0, 16)}…` : undefined,
      });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to export PDF");
    } finally {
      setExporting(false);
    }
  };

  const copyHash = async () => {
    const h = doc?.last_export?.sha256;
    if (!h) return;
    try {
      await navigator.clipboard.writeText(h);
      toast.success("SHA-256 copied to clipboard");
    } catch {
      toast.error("Couldn't copy — your browser blocked clipboard access");
    }
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get<DocResponse>("/admin/platform/security-doc")
      .then(({ data }) => {
        if (!cancelled) {
          setDoc(data);
          setErr(null);
        }
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = e?.response?.data?.detail || "Failed to load SECURITY.md";
        setErr(msg);
        toast.error(msg);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card className="bg-card border-border" data-testid="security-doc-panel">
      <CardHeader>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <ShieldCheck className="h-6 w-6 text-emerald-400" />
            <div>
              <CardTitle className="flex items-center gap-2">
                Security Conventions
                <Badge variant="outline" className="text-[10px] uppercase tracking-wider">
                  Admin-only
                </Badge>
              </CardTitle>
              <CardDescription>
                Repo-root <code className="rounded bg-secondary/60 px-1 text-[11px]">SECURITY.md</code> — threat model,
                seven-endpoint auth pattern, Socket.IO room allowlist, and the P3 hardening invariants. Rendered live
                so every team member sees the latest committed version.
              </CardDescription>
            </div>
          </div>
          {doc?.modified_at && (
            <div className="flex items-center gap-2 shrink-0">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Clock className="h-3 w-3" /> Updated {new Date(doc.modified_at).toLocaleString()}
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={handleExportPdf}
                disabled={exporting}
                data-testid="security-doc-export-pdf"
                className="gap-1.5"
              >
                {exporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                Export PDF
              </Button>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-4" data-testid="security-doc-loading">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading SECURITY.md…
          </div>
        )}
        {err && !loading && (
          <div className="flex items-center gap-2 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            <FileText className="h-4 w-4 shrink-0" />
            {err}
          </div>
        )}
        {!loading && doc && (
          <>
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground/70 mb-3">
              <FileText className="h-3 w-3" />
              <span className="font-mono">{doc.path}</span>
              <span>·</span>
              <span>{(doc.bytes / 1024).toFixed(1)} KB</span>
              <a
                href="https://owasp.org/Top10/"
                target="_blank"
                rel="noreferrer"
                className="ml-auto inline-flex items-center gap-1 hover:underline hover:text-cyan-400"
                data-testid="security-doc-owasp-link"
              >
                OWASP Top 10 <ExternalLink className="h-3 w-3" />
              </a>
            </div>
            {/* Iter 230p — Chain-of-custody hash row */}
            {doc.last_export?.sha256 && (
              <div
                className="flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/5 px-2.5 py-1.5 mb-4 text-[11px]"
                data-testid="security-doc-last-export"
              >
                <Hash className="h-3.5 w-3.5 text-emerald-300 shrink-0" />
                <span className="text-muted-foreground shrink-0">Last export:</span>
                <code
                  className="font-mono text-emerald-200 truncate"
                  title={doc.last_export.sha256}
                  data-testid="security-doc-last-export-hash"
                >
                  {doc.last_export.sha256}
                </code>
                <button
                  type="button"
                  onClick={copyHash}
                  data-testid="security-doc-copy-hash"
                  aria-label="Copy SHA-256"
                  title="Copy SHA-256 to clipboard"
                  className="h-5 w-5 rounded text-muted-foreground hover:text-emerald-300 hover:bg-white/5 flex items-center justify-center shrink-0"
                >
                  <Copy className="h-3 w-3" />
                </button>
                <span className="text-muted-foreground/70 shrink-0 ml-1">
                  · {new Date(doc.last_export.generated_at).toLocaleString()}
                </span>
                {doc.last_export.generated_by && (
                  <span className="text-muted-foreground/70 shrink-0">
                    · by <span className="text-foreground/80">{doc.last_export.generated_by}</span>
                  </span>
                )}
                <span className="text-muted-foreground/70 shrink-0 ml-auto">
                  Verify: <code className="font-mono text-foreground/80">shasum -a 256</code>
                </span>
              </div>
            )}
            <div data-testid="security-doc-content">{renderMarkdown(doc.content)}</div>
            <div className="mt-6 flex justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={() => window.location.reload()}
                data-testid="security-doc-refresh"
              >
                Refresh
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
